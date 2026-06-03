"""Kubernetes probes: pod readiness and deployment availability.

Each issues a `kubectl get ... -o json` through the provider and reads the result;
the KubernetesProvider supplies the kubectl/context/namespace prefix.
"""

from __future__ import annotations

import json
from typing import ClassVar

from spero.probes.base import Probe, ProbeResult
from spero.providers.base import Provider


class PodReadyProbe(Probe):
    """Healthy iff at least ``min_ready`` pods matching ``selector`` are Ready."""

    type: ClassVar[str] = "pod"

    def __init__(self, selector: str, min_ready: int = 1) -> None:
        if int(min_ready) < 1:
            raise ValueError("min_ready must be >= 1")
        self.selector = selector
        self.min_ready = int(min_ready)

    async def check(self, provider: Provider) -> ProbeResult:
        r = await provider.run(["get", "pods", "-l", self.selector, "-o", "json"], timeout=30)
        if not r.ok:
            return ProbeResult(False, f"kubectl get pods failed: {r.stderr.strip()}")
        try:
            items = json.loads(r.stdout).get("items", [])
        except json.JSONDecodeError as exc:
            return ProbeResult(False, f"could not parse kubectl json: {exc}")
        ready = sum(1 for pod in items if _pod_ready(pod))
        healthy = ready >= self.min_ready
        return ProbeResult(healthy, f"{ready}/{self.min_ready} ready for {self.selector!r}")


class DeploymentProbe(Probe):
    """Healthy iff the deployment's available replicas meet its desired count."""

    type: ClassVar[str] = "deployment"

    def __init__(self, name: str) -> None:
        self.name = name

    async def check(self, provider: Provider) -> ProbeResult:
        r = await provider.run(["get", "deployment", self.name, "-o", "json"], timeout=30)
        if not r.ok:
            return ProbeResult(False, f"kubectl get deployment failed: {r.stderr.strip()}")
        try:
            data = json.loads(r.stdout)
        except json.JSONDecodeError as exc:
            return ProbeResult(False, f"could not parse kubectl json: {exc}")
        desired = int(data.get("spec", {}).get("replicas", 0) or 0)
        available = int(data.get("status", {}).get("availableReplicas", 0) or 0)
        if desired == 0:  # intentionally scaled to zero: nothing wanted, nothing missing
            return ProbeResult(True, f"{self.name}: scaled to 0 (no replicas desired)")
        return ProbeResult(available >= desired, f"{self.name}: {available}/{desired} available")


def _pod_ready(pod: dict[str, object]) -> bool:
    status = pod.get("status", {})
    if not isinstance(status, dict) or status.get("phase") != "Running":
        return False
    conditions = status.get("conditions", [])
    if not isinstance(conditions, list):
        return False
    return any(
        isinstance(c, dict) and c.get("type") == "Ready" and c.get("status") == "True"
        for c in conditions
    )
