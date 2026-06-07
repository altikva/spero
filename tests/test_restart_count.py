# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# __creation__ = 2026-06-07
# __author__ = "jndjama (Joy Ndjama)"
# __copyright__ = "Copyright 2026 ALTIKVA."
# __licence__ = "MIT & CC BY-NC-SA (https://www.altikva.com/licenses/LICENSE-1.0)"
# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# Description: Tests for the restart-count probe (CrashLoopBackOff / OOMKilled / count).

"""Tests for spero.probes.kubernetes.RestartCountProbe."""

from __future__ import annotations

import json

from spero.probes.kubernetes import RestartCountProbe
from spero.providers.command import CommandResult


class _JsonProvider:
    def __init__(self, items: list[dict]) -> None:
        self._payload = json.dumps({"items": items})

    async def run(self, command: object, *, timeout: float | None = None) -> CommandResult:
        return CommandResult(0, self._payload, "")


def _pod(name: str, *, restarts: int = 0, waiting: str = "", last_term: str = "") -> dict:
    cs: dict = {"name": "app", "restartCount": restarts, "state": {}, "lastState": {}}
    if waiting:
        cs["state"] = {"waiting": {"reason": waiting}}
    if last_term:
        cs["lastState"] = {"terminated": {"reason": last_term}}
    return {"metadata": {"name": name}, "status": {"containerStatuses": [cs]}}


async def test_healthy_when_below_threshold() -> None:
    probe = RestartCountProbe(selector="app=web", max_restarts=5)
    result = await probe.check(_JsonProvider([_pod("web-1", restarts=2)]))  # type: ignore[arg-type]
    assert result.healthy


async def test_unhealthy_over_restart_threshold() -> None:
    probe = RestartCountProbe(selector="app=web", max_restarts=5)
    result = await probe.check(_JsonProvider([_pod("web-1", restarts=7)]))  # type: ignore[arg-type]
    assert not result.healthy
    assert "restarted 7x" in result.detail


async def test_crashloop_is_unhealthy_regardless_of_count() -> None:
    probe = RestartCountProbe(selector="app=web", max_restarts=99)
    result = await probe.check(  # type: ignore[arg-type]
        _JsonProvider([_pod("web-1", restarts=1, waiting="CrashLoopBackOff")])
    )
    assert not result.healthy
    assert "CrashLoopBackOff" in result.detail


async def test_oomkilled_is_unhealthy() -> None:
    probe = RestartCountProbe(selector="app=web", max_restarts=99)
    result = await probe.check(  # type: ignore[arg-type]
        _JsonProvider([_pod("web-1", restarts=1, last_term="OOMKilled")])
    )
    assert not result.healthy
    assert "OOMKilled" in result.detail


async def test_no_pods_is_healthy() -> None:
    result = await RestartCountProbe(selector="app=none").check(_JsonProvider([]))  # type: ignore[arg-type]
    assert result.healthy


def test_object_and_pod_ref() -> None:
    probe = RestartCountProbe(selector="app=web")
    assert probe.object_ref() == ["pods", "-l", "app=web"]
    assert probe.pod_ref() == ["-l", "app=web"]
