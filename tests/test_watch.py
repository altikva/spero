# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# __creation__ = 2026-06-03
# __author__ = "jndjama (Joy Ndjama)"
# __copyright__ = "Copyright 2026 ALTIKVA."
# __licence__ = "MIT & CC BY-NC-SA (http://www.altikva.com/licenses/LICENSE-1.0)"
# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#

"""Tests for the continuous watch loop and its scheduler wiring."""

from __future__ import annotations

import asyncio
from pathlib import Path

from _fakes import ScriptedProvider, systemd_handler
from spero.core.engine import Engine
from spero.core.policy import load_policy_str
from spero.core.watch import build_scheduler, watch
from spero.store import Event, init_db, make_engine, recent_events

POLICY = """
targets:
  - name: web
    provider: local
    probe: {type: systemd, params: {unit: nginx.service}, interval: 5}
  - name: db
    provider: local
    probe: {type: systemd, params: {unit: pg.service}, interval: 60}
"""


def _engine(provider: ScriptedProvider) -> Engine:
    return Engine(load_policy_str(POLICY), provider_factory=lambda _spec: provider)


async def test_build_scheduler_one_job_per_target_at_its_interval() -> None:
    engine = _engine(ScriptedProvider(systemd_handler(active=True)))
    scheduler = build_scheduler(engine, engine.policy)
    jobs = {j.id: j for j in scheduler.get_jobs()}
    assert set(jobs) == {"web", "db"}
    assert jobs["web"].trigger.interval.total_seconds() == 5
    assert jobs["db"].trigger.interval.total_seconds() == 60


async def test_tick_supervises_and_persists(tmp_path: Path) -> None:
    # one probe failure -> engine records an event -> persisted to the store.
    # File-backed (not :memory:) because the async persist commits in a worker thread.
    provider = ScriptedProvider(systemd_handler(active=False))
    engine = _engine(provider)
    store_engine = make_engine(f"sqlite:///{tmp_path / 'spero.db'}")
    init_db(store_engine)

    outcomes: list[str] = []
    stop = asyncio.Event()

    def on_outcome(o: object) -> None:
        outcomes.append("seen")
        stop.set()  # stop as soon as the first tick lands

    await asyncio.wait_for(
        watch(engine, engine.policy, store_engine=store_engine, on_outcome=on_outcome, stop=stop),
        timeout=5,
    )
    assert outcomes  # at least one tick fired
    events: list[Event] = recent_events(store_engine)
    assert any(e.kind == "probe_fail" for e in events)


async def test_watch_returns_when_stopped_immediately() -> None:
    engine = _engine(ScriptedProvider(systemd_handler(active=True)))
    stop = asyncio.Event()
    stop.set()  # already stopped -> watch should return promptly
    await asyncio.wait_for(watch(engine, engine.policy, stop=stop), timeout=5)
