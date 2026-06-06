# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# __creation__ = 2026-06-05
# __author__ = "jndjama (Joy Ndjama)"
# __copyright__ = "Copyright 2026 ALTIKVA."
# __licence__ = "MIT & CC BY-NC-SA (https://www.altikva.com/licenses/LICENSE-1.0)"
# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# Description: Tests for the elpio probes against elpio v0.1.0's real status shape.

"""Tests for the elpio CRD probes (status.ready + Ready condition, group elpio.io)."""

from __future__ import annotations

import json

import pytest

from _fakes import ScriptedProvider, fixed
from spero.core.models import ProbeSpec
from spero.probes import build_probe
from spero.probes.elpio import ElpioFunctionProbe, ElpioServiceProbe, ElpioTaskProbe


def _status(ready: bool, *, reason: str = "", **extra: object) -> str:
    # Mirrors elpio's real status: a `ready` bool plus a Ready condition ("True"/"False").
    status: dict = {
        "ready": ready,
        "conditions": [{"type": "Ready", "status": "True" if ready else "False", "reason": reason}],
        **extra,
    }
    return json.dumps({"status": status})


# --- ElpioService ---


async def test_service_ready_names_engine() -> None:
    provider = ScriptedProvider(fixed(0, _status(True, engine="knative")))
    r = await ElpioServiceProbe("orders").check(provider)
    assert r.healthy
    assert "on knative" in r.detail
    assert provider.commands == [["get", "elpioservice.elpio.io", "orders", "-o", "json"]]


async def test_service_ready_via_condition_only() -> None:
    # No `ready` bool, only the Ready condition -> still healthy (fallback path).
    body = json.dumps({"status": {"conditions": [{"type": "Ready", "status": "True"}]}})
    r = await ElpioServiceProbe("orders").check(ScriptedProvider(fixed(0, body)))
    assert r.healthy


async def test_service_not_ready_surfaces_reason() -> None:
    r = await ElpioServiceProbe("orders").check(
        ScriptedProvider(fixed(0, _status(False, reason="ImagePullBackOff")))
    )
    assert not r.healthy
    assert "not ready" in r.detail
    assert "ImagePullBackOff" in r.detail


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


# --- ElpioFunction ---


async def test_function_ready_names_service() -> None:
    provider = ScriptedProvider(fixed(0, _status(True, serviceName="orders-svc")))
    r = await ElpioFunctionProbe("orders-fn").check(provider)
    assert r.healthy
    assert "orders-svc" in r.detail
    assert provider.commands == [["get", "elpiofunction.elpio.io", "orders-fn", "-o", "json"]]


async def test_function_build_failure_surfaces_reason() -> None:
    r = await ElpioFunctionProbe("orders-fn").check(
        ScriptedProvider(fixed(0, _status(False, reason="BuildFailed", phase="BuildFailed")))
    )
    assert not r.healthy
    assert "not ready" in r.detail
    assert "BuildFailed" in r.detail


# --- ElpioTask ---


async def test_task_ready_with_backlog() -> None:
    r = await ElpioTaskProbe("emails").check(
        ScriptedProvider(fixed(0, _status(True, queueLength=42)))
    )
    assert r.healthy
    assert "42 queued" in r.detail
    assert "elpiotask.elpio.io" not in r.detail  # detail is human text, not the resource


async def test_task_ready_no_backlog() -> None:
    r = await ElpioTaskProbe("emails").check(ScriptedProvider(fixed(0, _status(True))))
    assert r.healthy
    assert "ready" in r.detail


async def test_task_not_ready_is_unhealthy() -> None:
    r = await ElpioTaskProbe("emails").check(
        ScriptedProvider(fixed(0, _status(False, reason="DispatcherCrashLoop")))
    )
    assert not r.healthy
    assert "not ready" in r.detail


def test_registry_builds_function_and_task() -> None:
    assert isinstance(
        build_probe(ProbeSpec(type="elpio-function", params={"name": "f"})), ElpioFunctionProbe
    )
    assert isinstance(
        build_probe(ProbeSpec(type="elpio-task", params={"name": "t"})), ElpioTaskProbe
    )
