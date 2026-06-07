# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# __creation__ = 2026-06-07
# __author__ = "jndjama (Joy Ndjama)"
# __copyright__ = "Copyright 2026 ALTIKVA."
# __licence__ = "MIT & CC BY-NC-SA (https://www.altikva.com/licenses/LICENSE-1.0)"
# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# Description: Tests for the pvc probe (Bound is healthy, anything else is not).

"""Tests for spero.probes.kubernetes.PvcProbe."""

from __future__ import annotations

import json

from spero.providers.command import CommandResult


class _JsonProvider:
    def __init__(self, status: dict, *, ok: bool = True, stderr: str = "") -> None:
        self._payload = json.dumps({"status": status})
        self._ok = ok
        self._stderr = stderr

    async def run(self, command: object, *, timeout: float | None = None) -> CommandResult:
        return CommandResult(0 if self._ok else 1, self._payload if self._ok else "", self._stderr)


async def test_bound_is_healthy_with_capacity() -> None:
    from spero.probes.kubernetes import PvcProbe

    status = {"phase": "Bound", "capacity": {"storage": "10Gi"}}
    result = await PvcProbe(name="data").check(_JsonProvider(status))  # type: ignore[arg-type]
    assert result.healthy
    assert "Bound" in result.detail
    assert "10Gi" in result.detail


async def test_pending_is_unhealthy() -> None:
    from spero.probes.kubernetes import PvcProbe

    result = await PvcProbe(name="data").check(_JsonProvider({"phase": "Pending"}))  # type: ignore[arg-type]
    assert not result.healthy
    assert "Pending" in result.detail


async def test_missing_phase_is_unhealthy() -> None:
    from spero.probes.kubernetes import PvcProbe

    result = await PvcProbe(name="data").check(_JsonProvider({}))  # type: ignore[arg-type]
    assert not result.healthy
    assert "Unknown" in result.detail


async def test_kubectl_failure_is_unhealthy() -> None:
    from spero.probes.kubernetes import PvcProbe

    provider = _JsonProvider({}, ok=False, stderr="not found")
    result = await PvcProbe(name="data").check(provider)  # type: ignore[arg-type]
    assert not result.healthy
    assert "not found" in result.detail


def test_object_ref() -> None:
    from spero.probes.kubernetes import PvcProbe

    assert PvcProbe(name="data").object_ref() == ["pvc", "data"]


def test_build_from_spec() -> None:
    from spero.core.models import ProbeSpec
    from spero.probes import build_probe
    from spero.probes.kubernetes import PvcProbe

    probe = build_probe(ProbeSpec(type="pvc", params={"name": "data"}))
    assert isinstance(probe, PvcProbe)
    assert probe.name == "data"
