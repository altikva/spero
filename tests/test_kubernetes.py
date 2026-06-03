"""Tests for the Kubernetes provider, probes, and remediations (kubectl-backed)."""

from __future__ import annotations

import json

from _fakes import ScriptedProvider, fixed
from spero.probes.kubernetes import DeploymentProbe, PodReadyProbe
from spero.providers.host import make_provider
from spero.providers.kubernetes import KubernetesProvider
from spero.remediations.kubernetes import DeletePod, RolloutRestart, ScaleDeployment

PODS_JSON = json.dumps(
    {
        "items": [
            {"status": {"phase": "Running", "conditions": [{"type": "Ready", "status": "True"}]}},
            {"status": {"phase": "Running", "conditions": [{"type": "Ready", "status": "False"}]}},
        ]
    }
)
DEPLOY_JSON = json.dumps({"spec": {"replicas": 3}, "status": {"availableReplicas": 3}})
DEPLOY_DEGRADED = json.dumps({"spec": {"replicas": 3}, "status": {"availableReplicas": 1}})


def test_make_provider_k8s_variants() -> None:
    assert isinstance(make_provider("k8s"), KubernetesProvider)
    p = make_provider("k8s:prod/web")
    assert isinstance(p, KubernetesProvider)
    assert p.context == "prod"
    assert p.namespace == "web"
    assert make_provider("k8s:/web").namespace == "web"
    assert make_provider("k8s:prod").context == "prod"


def test_kubectl_prefix() -> None:
    p = KubernetesProvider(context="prod", namespace="web")
    assert p.prefix() == ["kubectl", "--context", "prod", "-n", "web"]
    assert KubernetesProvider().prefix() == ["kubectl"]


async def test_pod_ready_probe() -> None:
    provider = ScriptedProvider(fixed(0, PODS_JSON))
    r = await PodReadyProbe(selector="app=web", min_ready=1).check(provider)
    assert r.healthy  # one of two pods is Ready
    assert provider.commands == [["get", "pods", "-l", "app=web", "-o", "json"]]


async def test_pod_ready_probe_below_min() -> None:
    r = await PodReadyProbe(selector="app=web", min_ready=2).check(
        ScriptedProvider(fixed(0, PODS_JSON))
    )
    assert not r.healthy


async def test_deployment_probe() -> None:
    assert (await DeploymentProbe("web").check(ScriptedProvider(fixed(0, DEPLOY_JSON)))).healthy
    assert not (
        await DeploymentProbe("web").check(ScriptedProvider(fixed(0, DEPLOY_DEGRADED)))
    ).healthy


async def test_probe_handles_kubectl_failure() -> None:
    r = await DeploymentProbe("web").check(ScriptedProvider(fixed(1, "", "not found")))
    assert not r.healthy
    assert "failed" in r.detail


async def test_rollout_restart() -> None:
    provider = ScriptedProvider(fixed(0))
    await RolloutRestart("web").apply(provider)
    assert provider.commands == [["rollout", "restart", "deployment/web"]]


async def test_scale_and_delete() -> None:
    sp = ScriptedProvider(fixed(0))
    await ScaleDeployment("web", 5).apply(sp)
    assert sp.commands == [["scale", "deployment/web", "--replicas=5"]]
    dp = ScriptedProvider(fixed(0))
    await DeletePod("app=web").apply(dp)
    assert dp.commands == [["delete", "pod", "-l", "app=web"]]
