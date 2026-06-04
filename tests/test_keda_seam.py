# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# __creation__ = 2026-06-04
# __author__ = "jndjama (Joy Ndjama)"
# __copyright__ = "Copyright 2026 ALTIKVA."
# __licence__ = "MIT & CC BY-NC-SA (http://www.altikva.com/licenses/LICENSE-1.0)"
# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# Description: Tests for the EXPERIMENTAL KEDA seam spike (docs/experiments/0001-keda-seam.md).

"""Tests for the EXPERIMENTAL KEDA seam spike (docs/experiments/0001-keda-seam.md).

Covers the two halves that fit spero's seams: the ScaledObject readiness probe and
the unpause remediation, plus that both build from a policy through the registries.
"""

from __future__ import annotations

import json

import pytest

from _fakes import ScriptedProvider, fixed
from spero.core.models import ProbeSpec, RemediationSpec
from spero.probes import build_probe
from spero.probes.keda import KedaScaledObjectProbe
from spero.remediations import build_remediation
from spero.remediations.keda import UnpauseScaledObject


def _scaledobject(ready: str, active: str, paused: str = "False") -> str:
    # Mirrors live KEDA: Ready/Active/Paused conditions (verified against KEDA on
    # minikube -- pausing sets Paused=True but keeps Ready=True).
    return json.dumps(
        {
            "status": {
                "conditions": [
                    {"type": "Ready", "status": ready},
                    {"type": "Active", "status": active},
                    {"type": "Paused", "status": paused},
                ]
            }
        }
    )


async def test_ready_and_active_is_healthy() -> None:
    provider = ScriptedProvider(fixed(0, _scaledobject("True", "True")))
    r = await KedaScaledObjectProbe("orders-api").check(provider)
    assert r.healthy
    assert "active" in r.detail
    assert provider.commands == [["get", "scaledobject", "orders-api", "-o", "json"]]


async def test_ready_but_scaled_to_zero_is_healthy() -> None:
    # Idle serverless workload: Ready but Active=False. Healthy, mirroring DeploymentProbe.
    r = await KedaScaledObjectProbe("orders-api").check(
        ScriptedProvider(fixed(0, _scaledobject("True", "False")))
    )
    assert r.healthy
    assert "scaled-to-zero" in r.detail


async def test_paused_is_unhealthy_even_when_ready() -> None:
    # KEDA keeps Ready=True when paused; the probe must still flag it so the engine
    # fires UnpauseScaledObject. Without this, a frozen autoscaler reads as healthy.
    r = await KedaScaledObjectProbe("orders-api").check(
        ScriptedProvider(fixed(0, _scaledobject("True", "True", paused="True")))
    )
    assert not r.healthy
    assert "paused" in r.detail


async def test_not_ready_is_unhealthy() -> None:
    r = await KedaScaledObjectProbe("orders-api").check(
        ScriptedProvider(fixed(0, _scaledobject("False", "False")))
    )
    assert not r.healthy
    assert "not Ready" in r.detail


async def test_probe_handles_kubectl_failure() -> None:
    r = await KedaScaledObjectProbe("orders-api").check(ScriptedProvider(fixed(1, "", "NotFound")))
    assert not r.healthy
    assert "failed" in r.detail


async def test_probe_handles_bad_json() -> None:
    r = await KedaScaledObjectProbe("orders-api").check(ScriptedProvider(fixed(0, "not json")))
    assert not r.healthy
    assert "parse" in r.detail


async def test_unpause_clears_both_annotations() -> None:
    provider = ScriptedProvider(fixed(0))
    res = await UnpauseScaledObject("orders-api").apply(provider)
    assert res.success
    assert provider.commands == [
        [
            "annotate",
            "scaledobject/orders-api",
            "autoscaling.keda.sh/paused-",
            "autoscaling.keda.sh/paused-replicas-",
            "--overwrite",
        ]
    ]


async def test_unpause_reports_kubectl_failure() -> None:
    res = await UnpauseScaledObject("orders-api").apply(ScriptedProvider(fixed(1, "", "boom")))
    assert not res.success
    assert "boom" in res.detail


def test_unpause_is_not_destructive() -> None:
    # It only clears annotations; nothing is deleted, so autonomy=auto stays legal.
    assert UnpauseScaledObject.destructive is False


def test_registries_build_keda_seam_from_policy() -> None:
    probe = build_probe(ProbeSpec(type="keda-scaledobject", params={"name": "orders-api"}))
    assert isinstance(probe, KedaScaledObjectProbe)
    rem = build_remediation(RemediationSpec(type="keda-unpause", params={"name": "orders-api"}))
    assert isinstance(rem, UnpauseScaledObject)


def test_bad_params_rejected_at_build() -> None:
    with pytest.raises(ValueError, match="bad params"):
        build_probe(ProbeSpec(type="keda-scaledobject", params={"wrong": "x"}))
