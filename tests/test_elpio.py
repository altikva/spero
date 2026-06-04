# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# __creation__ = 2026-06-05
# __author__ = "jndjama (Joy Ndjama)"
# __copyright__ = "Copyright 2026 ALTIKVA."
# __licence__ = "MIT & CC BY-NC-SA (https://www.altikva.com/licenses/LICENSE-1.0)"
# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# Description: Tests for ElpioServiceProbe -- Ready/NotReady, scaled-to-zero, and policy build.

"""Tests for the EXPERIMENTAL ElpioService probe (elpio day-2 supervision)."""

from __future__ import annotations

import json

import pytest

from _fakes import ScriptedProvider, fixed
from spero.core.models import ProbeSpec
from spero.probes import build_probe
from spero.probes.elpio import ElpioServiceProbe


def _svc(ready: str, *, revision: str | None = None, extra: list[dict] | None = None) -> str:
    conditions = [{"type": "Ready", "status": ready}]
    if extra:
        conditions += extra
    status: dict = {"conditions": conditions}
    if revision:
        status["latestReadyRevisionName"] = revision
    return json.dumps({"status": status})


async def test_ready_is_healthy() -> None:
    provider = ScriptedProvider(fixed(0, _svc("True", revision="orders-00003")))
    r = await ElpioServiceProbe("orders").check(provider)
    assert r.healthy
    assert "orders-00003" in r.detail
    assert provider.commands == [["get", "elpioservice", "orders", "-o", "json"]]


async def test_ready_without_revision_still_healthy() -> None:
    r = await ElpioServiceProbe("orders").check(ScriptedProvider(fixed(0, _svc("True"))))
    assert r.healthy
    assert "Ready" in r.detail


async def test_not_ready_surfaces_failing_subcondition() -> None:
    body = _svc(
        "False",
        extra=[{"type": "RoutesReady", "status": "False", "reason": "IngressNotConfigured"}],
    )
    r = await ElpioServiceProbe("orders").check(ScriptedProvider(fixed(0, body)))
    assert not r.healthy
    assert "not Ready" in r.detail
    assert "RoutesReady" in r.detail
    assert "IngressNotConfigured" in r.detail


async def test_kubectl_failure_is_unhealthy() -> None:
    r = await ElpioServiceProbe("orders").check(ScriptedProvider(fixed(1, "", "NotFound")))
    assert not r.healthy
    assert "failed" in r.detail


async def test_bad_json_is_unhealthy() -> None:
    r = await ElpioServiceProbe("orders").check(ScriptedProvider(fixed(0, "not json")))
    assert not r.healthy
    assert "parse" in r.detail


def test_registry_builds_from_policy() -> None:
    probe = build_probe(ProbeSpec(type="elpio-service", params={"name": "orders"}))
    assert isinstance(probe, ElpioServiceProbe)


def test_bad_params_rejected() -> None:
    with pytest.raises(ValueError, match="bad params"):
        build_probe(ProbeSpec(type="elpio-service", params={"wrong": "x"}))
