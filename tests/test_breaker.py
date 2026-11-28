# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# __creation__ = 2026-11-28
# __author__ = "jndjama (Joy Ndjama)"
# __copyright__ = "Copyright 2026 ALTIKVA."
# __licence__ = "Apache-2.0 (https://www.apache.org/licenses/LICENSE-2.0)"
# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# Description: Tests for the crash-loop breaker: trip, window, reset, persistence.

"""Tests for the crash-loop breaker: trip, window, reset, persistence."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from _fakes import ScriptedProvider, systemd_handler
from spero.alerting.base import Alerter
from spero.core.breaker import BreakerStore, MemoryBreakerStore
from spero.core.engine import Engine
from spero.core.policy import load_policy_str
from spero.store import init_db, make_engine
from spero.store.breaker import SQLBreakerStore

POLICY = """
targets:
  - name: web
    probe: {type: systemd, params: {unit: nginx.service}}
    breaker: {max_restarts: 3, window_s: 60}
    remediations:
      - {type: restart, params: {unit: nginx.service}, autonomy: auto, max_attempts: 1}
"""


class Clock:
    def __init__(self) -> None:
        self.now = 1_000_000.0

    def __call__(self) -> float:
        return self.now


class RecordingAlerter(Alerter):
    def __init__(self) -> None:
        self.fired: list[str] = []

    async def fire(self, target: str, detail: str) -> None:
        self.fired.append(detail)

    async def resolve(self, target: str, detail: str) -> None:
        pass


def _engine(store: BreakerStore, clock: Clock, alerter: Alerter | None = None) -> Engine:
    provider = ScriptedProvider(systemd_handler(active=False, restart_ok=True))
    return Engine(
        load_policy_str(POLICY),
        provider_factory=lambda _spec: provider,
        breaker_store=store,
        clock=clock,
        alerter=alerter,
    )


async def _statuses(engine: Engine, clock: Clock, cycles: int, step: float = 5) -> list[str]:
    out = []
    for _ in range(cycles):
        (o,) = await engine.run_cycle()
        assert o.action is not None
        out.append(o.action.status.value)
        clock.now += step
    return out


async def test_fourth_death_in_window_trips_and_stops_restarting() -> None:
    clock, alerter = Clock(), RecordingAlerter()
    engine = _engine(MemoryBreakerStore(), clock, alerter)
    statuses = await _statuses(engine, clock, 6)
    assert statuses == ["applied", "applied", "applied", "tripped", "tripped", "tripped"]
    assert [e.kind for e in engine.events].count("breaker") == 1  # one event, at the trip
    assert any("restart breaker tripped" in d for d in alerter.fired)


async def test_restarts_spread_beyond_the_window_never_trip() -> None:
    clock = Clock()
    engine = _engine(MemoryBreakerStore(), clock)
    assert set(await _statuses(engine, clock, 8, step=25)) == {"applied"}


async def test_tripped_state_survives_a_new_engine_and_needs_an_explicit_reset(
    tmp_path: Path,
) -> None:
    db = make_engine(f"sqlite:///{tmp_path / 'spero.db'}")
    init_db(db)
    clock = Clock()
    await _statuses(_engine(SQLBreakerStore(db), clock), clock, 4)

    # A restarted daemon (new engine, same store) stays tripped, even much later.
    clock.now += 3600
    restarted = _engine(SQLBreakerStore(db), clock)
    assert await _statuses(restarted, clock, 2) == ["tripped", "tripped"]

    assert SQLBreakerStore(db).reset("web") is True
    assert SQLBreakerStore(db).reset("web") is False
    assert (await _statuses(restarted, clock, 1)) == ["applied"]


async def test_target_without_breaker_is_unchanged() -> None:
    clock = Clock()
    engine = Engine(
        load_policy_str(POLICY.replace("    breaker: {max_restarts: 3, window_s: 60}\n", "")),
        provider_factory=lambda _s: ScriptedProvider(systemd_handler(False, restart_ok=True)),
        clock=clock,
    )
    assert set(await _statuses(engine, clock, 6)) == {"applied"}


@pytest.mark.parametrize("breaker", ["{max_restarts: 0, window_s: 60}", "{max_restarts: 3}"])
def test_bad_breaker_rejected_at_load(breaker: str) -> None:
    with pytest.raises(ValidationError):
        load_policy_str(POLICY.replace("{max_restarts: 3, window_s: 60}", breaker))


def test_reset_command(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from spero.cli import app
    from spero.config import settings

    url = f"sqlite:///{tmp_path / 'spero.db'}"
    monkeypatch.setattr(settings, "database_url", url)
    db = make_engine(url)
    init_db(db)
    store = SQLBreakerStore(db)
    state = store.load("web")
    state.tripped_at, state.detail = 1.0, "3 restarts within 60s"
    store.save("web", state)

    result = CliRunner().invoke(app, ["reset", "web"])
    assert result.exit_code == 0, result.output
    assert "breaker reset" in result.output
    assert not store.load("web").tripped
