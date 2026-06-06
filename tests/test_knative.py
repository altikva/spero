# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# __creation__ = 2026-06-05
# __author__ = "jndjama (Joy Ndjama)"
# __copyright__ = "Copyright 2026 ALTIKVA."
# __licence__ = "MIT & CC BY-NC-SA (https://www.altikva.com/licenses/LICENSE-1.0)"
# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# Description: Tests for KnativeServiceProbe -- Ready/NotReady, revisions, and policy build.

"""Tests for the EXPERIMENTAL Knative Service probe (serving.knative.dev supervision)."""

from __future__ import annotations

import json

import pytest

from _fakes import ScriptedProvider, fixed
from spero.core.models import ProbeSpec
from spero.probes import build_probe
from spero.probes.knative import KnativeServiceProbe


def _ksvc(ready: str, *, revision: str | None = None, extra: list[dict] | None = None) -> str:
    conditions = [{"type": "Ready", "status": ready}]
    if extra:
        conditions += extra
    status: dict = {"conditions": conditions}
    if revision:
        status["latestReadyRevisionName"] = revision
    return json.dumps({"status": status})


async def test_ready_with_revision_is_healthy() -> None:
    provider = ScriptedProvider(fixed(0, _ksvc("True", revision="web-00007")))
    r = await KnativeServiceProbe("web").check(provider)
    assert r.healthy
    assert "web-00007" in r.detail
    assert provider.commands == [["get", "ksvc", "web", "-o", "json"]]


async def test_ready_without_revision_still_healthy() -> None:
    r = await KnativeServiceProbe("web").check(ScriptedProvider(fixed(0, _ksvc("True"))))
    assert r.healthy
    assert "Ready" in r.detail


async def test_not_ready_surfaces_failing_subcondition() -> None:
    body = _ksvc(
        "False",
        extra=[
            {"type": "ConfigurationsReady", "status": "False", "reason": "RevisionFailed"},
            {"type": "RoutesReady", "status": "False", "reason": "IngressNotConfigured"},
        ],
    )
    r = await KnativeServiceProbe("web").check(ScriptedProvider(fixed(0, body)))
    assert not r.healthy
    assert "not Ready" in r.detail
    assert "ConfigurationsReady" in r.detail
    assert "RevisionFailed" in r.detail


async def test_kubectl_failure_is_unhealthy() -> None:
    r = await KnativeServiceProbe("web").check(ScriptedProvider(fixed(1, "", "NotFound")))
    assert not r.healthy
    assert "failed" in r.detail


async def test_bad_json_is_unhealthy() -> None:
    r = await KnativeServiceProbe("web").check(ScriptedProvider(fixed(0, "not json")))
    assert not r.healthy
    assert "parse" in r.detail


def test_registry_builds_from_policy() -> None:
    probe = build_probe(ProbeSpec(type="knative-service", params={"name": "web"}))
    assert isinstance(probe, KnativeServiceProbe)


def test_bad_params_rejected() -> None:
    with pytest.raises(ValueError, match="bad params"):
        build_probe(ProbeSpec(type="knative-service", params={"wrong": "x"}))
