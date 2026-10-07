# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# __creation__ = 2026-10-07
# __author__ = "jndjama (Joy Ndjama)"
# __copyright__ = "Copyright 2026 ALTIKVA."
# __licence__ = "MIT & CC BY-NC-SA (https://www.altikva.com/licenses/LICENSE-1.0)"
# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# Description: Tests for reloading the policy in a running supervisor:
#              Engine.apply_policy (state kept, reset or dropped per target),
#              PolicyReloader (settling, bad files), the scheduler reconcile,
#              and the watch loop and CLI wiring around them.

"""Tests for reloading the policy in a running supervisor."""

from __future__ import annotations

import asyncio
import os
import signal
import sys
from pathlib import Path

import pytest

from _fakes import ScriptedProvider, systemd_handler
from spero.alerting.base import Alerter
from spero.cli import _run_watch
from spero.core.engine import Engine, PolicyChange
from spero.core.policy import PolicyReloader, PolicyReloadError, load_policy_str
from spero.core.watch import build_scheduler, reconcile_scheduler, watch


def _target(name: str, unit: str | None = None, interval: int = 5) -> str:
    return (
        f"  - name: {name}\n"
        f"    provider: local\n"
        f"    probe: {{type: systemd, params: {{unit: {unit or name}.service}}, "
        f"interval: {interval}}}\n"
    )


def _policy(*targets: str) -> str:
    return "targets:\n" + "".join(targets) if targets else "targets: []\n"


class SpyAlerter(Alerter):
    def __init__(self) -> None:
        self.fired: list[str] = []
        self.resolved: list[tuple[str, str]] = []

    async def fire(self, target: str, detail: str) -> None:
        self.fired.append(target)

    async def resolve(self, target: str, detail: str) -> None:
        self.resolved.append((target, detail))


def _engine(text: str, *, active: bool = False, alerter: Alerter | None = None) -> Engine:
    provider = ScriptedProvider(systemd_handler(active=active))
    return Engine(load_policy_str(text), provider_factory=lambda _spec: provider, alerter=alerter)


async def test_apply_policy_keeps_state_of_unchanged_targets() -> None:
    alerter = SpyAlerter()
    engine = _engine(_policy(_target("web"), _target("db")), alerter=alerter)
    await engine.run_cycle()
    await engine.run_cycle()
    assert engine.failures("web") == 2

    change = await engine.apply_policy(
        load_policy_str(_policy(_target("web"), _target("db"), _target("cache")))
    )

    assert change == PolicyChange(added=("cache",))
    assert engine.failures("web") == 2  # a reload must not delay an escalation
    await engine.run_cycle()
    assert engine.failures("web") == 3
    assert alerter.fired.count("web") == 1  # still the same open alert


async def test_apply_policy_resolves_alert_of_removed_target() -> None:
    alerter = SpyAlerter()
    engine = _engine(_policy(_target("web"), _target("db")), alerter=alerter)
    await engine.run_cycle()

    change = await engine.apply_policy(load_policy_str(_policy(_target("web"))))

    assert change == PolicyChange(removed=("db",))
    assert engine.failures("db") == 0
    assert alerter.resolved == [("db", "removed from policy")]
    assert [t.name for t in engine.policy.targets] == ["web"]


async def test_apply_policy_restarts_counter_of_changed_target() -> None:
    alerter = SpyAlerter()
    engine = _engine(_policy(_target("web")), alerter=alerter)
    await engine.run_cycle()
    await engine.run_cycle()

    change = await engine.apply_policy(load_policy_str(_policy(_target("web", unit="nginx"))))

    assert change == PolicyChange(changed=("web",))
    assert engine.failures("web") == 0
    await engine.run_cycle()
    assert alerter.fired == ["web"]  # still failing: no second alert
    assert alerter.resolved == []


async def test_probe_in_flight_for_removed_target_writes_no_state() -> None:
    engine = _engine(_policy(_target("web"), _target("db")))
    gone = engine.policy.targets[1]
    await engine.apply_policy(load_policy_str(_policy(_target("web"))))

    outcome = await engine.supervise(gone)  # the tick that was already scheduled

    assert outcome.healthy is False
    assert engine.failures("db") == 0
    # A target that comes back under the same name is supervised again.
    await engine.apply_policy(load_policy_str(_policy(_target("web"), _target("db"))))
    await engine.supervise(engine.policy.targets[1])
    assert engine.failures("db") == 1


def test_reloader_force_reads_at_once(tmp_path: Path) -> None:
    path = tmp_path / "p.yaml"
    path.write_text(_policy(_target("web")))
    reloader = PolicyReloader(path)
    assert reloader.poll() is None  # not watching the file: only a forced poll reads
    path.write_text(_policy(_target("web"), _target("db")))
    assert reloader.poll() is None
    policy = reloader.poll(force=True)
    assert policy is not None and [t.name for t in policy.targets] == ["web", "db"]


def test_reloader_waits_for_the_file_to_settle(tmp_path: Path) -> None:
    path = tmp_path / "p.yaml"
    path.write_text(_policy(_target("web")))
    reloader = PolicyReloader(path, on_change=True)
    assert reloader.poll() is None  # unchanged

    path.write_text(_policy(_target("web"), _target("db")))
    assert reloader.poll() is None  # first sight of the new bytes: may still be written
    policy = reloader.poll()  # same signature twice: settled
    assert policy is not None and len(policy.targets) == 2
    assert reloader.poll() is None  # already applied


def test_reloader_rejects_bad_files_once(tmp_path: Path) -> None:
    path = tmp_path / "p.yaml"
    path.write_text(_policy(_target("web")))
    reloader = PolicyReloader(path, on_change=True)

    path.write_text("")  # what a shell redirection leaves for an instant
    assert reloader.poll() is None
    with pytest.raises(PolicyReloadError, match="empty"):
        reloader.poll()
    assert reloader.poll() is None  # reported once, not on every poll

    path.write_text("targets:\n  - name: web\n    probe: {type: nope}\n")
    with pytest.raises(PolicyReloadError):
        reloader.poll(force=True)

    path.unlink()
    with pytest.raises(PolicyReloadError):
        reloader.poll(force=True)


async def test_reconcile_scheduler_touches_only_what_changed() -> None:
    engine = _engine(_policy(_target("web"), _target("db"), _target("old")))
    scheduler = build_scheduler(engine, engine.policy)
    web_job = scheduler.get_job("web")

    new = load_policy_str(_policy(_target("web"), _target("db", interval=60), _target("new")))
    change = await engine.apply_policy(new)
    reconcile_scheduler(scheduler, engine, new, change)

    jobs = {j.id: j for j in scheduler.get_jobs()}
    assert set(jobs) == {"web", "db", "new"}
    assert jobs["web"] is web_job or jobs["web"].trigger is web_job.trigger
    assert jobs["db"].trigger.interval.total_seconds() == 60


async def test_watch_reloads_on_request_and_survives_a_bad_file(tmp_path: Path) -> None:
    path = tmp_path / "p.yaml"
    path.write_text(_policy(_target("web")))
    engine = _engine(path.read_text(), active=True)
    stop, reload_now = asyncio.Event(), asyncio.Event()
    seen: asyncio.Queue[object] = asyncio.Queue()
    task = asyncio.create_task(
        watch(
            engine,
            engine.policy,
            stop=stop,
            reloader=PolicyReloader(path),
            reload_now=reload_now,
            on_reload=seen.put_nowait,
            poll_interval=0.05,
        )
    )

    path.write_text(_policy(_target("web"), _target("db")))
    reload_now.set()
    assert await asyncio.wait_for(seen.get(), 5) == PolicyChange(added=("db",))

    path.write_text("targets: [")
    reload_now.set()
    assert isinstance(await asyncio.wait_for(seen.get(), 5), PolicyReloadError)
    assert [t.name for t in engine.policy.targets] == ["web", "db"]  # old policy kept
    assert not task.done()

    stop.set()
    await asyncio.wait_for(task, 5)


async def test_watch_picks_up_a_changed_file(tmp_path: Path) -> None:
    path = tmp_path / "p.yaml"
    path.write_text(_policy(_target("web")))
    engine = _engine(path.read_text(), active=True)
    stop = asyncio.Event()
    seen: asyncio.Queue[object] = asyncio.Queue()
    task = asyncio.create_task(
        watch(
            engine,
            engine.policy,
            stop=stop,
            reloader=PolicyReloader(path, on_change=True),
            on_reload=seen.put_nowait,
            poll_interval=0.05,
        )
    )

    path.write_text(_policy())
    assert await asyncio.wait_for(seen.get(), 5) == PolicyChange(removed=("web",))

    stop.set()
    await asyncio.wait_for(task, 5)


@pytest.mark.skipif(sys.platform == "win32", reason="no SIGHUP on Windows")
async def test_cli_watch_reloads_on_sighup(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    path = tmp_path / "p.yaml"
    path.write_text(_policy(_target("web")))

    async def fake_watch(*_args: object, **kw: object) -> None:
        reloader, reload_now = kw["reloader"], kw["reload_now"]
        assert isinstance(reloader, PolicyReloader) and reloader.path == path
        assert isinstance(reload_now, asyncio.Event)
        os.kill(os.getpid(), signal.SIGHUP)
        await asyncio.wait_for(reload_now.wait(), timeout=5)

    monkeypatch.setattr("spero.core.watch.watch", fake_watch)
    await _run_watch(
        load_policy_str(path.read_text()), ai_approve=False, store=False, policy_path=str(path)
    )
