# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# __creation__ = 2026-06-03
# __author__ = "jndjama (Joy Ndjama)"
# __copyright__ = "Copyright 2026 ALTIKVA."
# __licence__ = "MIT & CC BY-NC-SA (https://www.altikva.com/licenses/LICENSE-1.0)"
# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# Description: Kubernetes probes: pod readiness and deployment availability.

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

    def object_ref(self) -> list[str]:
        return ["pods", "-l", self.selector]

    def pod_ref(self) -> list[str]:
        return ["-l", self.selector]

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

    def object_ref(self) -> list[str]:
        return ["deployment", self.name]

    def pod_ref(self) -> list[str]:
        return [f"deployment/{self.name}"]

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


class RestartCountProbe(Probe):
    """Unhealthy if any pod matching ``selector`` is crash-looping.

    Flags a container that is in ``CrashLoopBackOff``, was ``OOMKilled``, or has
    restarted at least ``max_restarts`` times. These are the common "the pod is up
    but unhealthy" signals that a plain readiness check can miss between restarts.
    The detail names the worst container and why.
    """

    type: ClassVar[str] = "restart-count"

    def __init__(self, selector: str, max_restarts: int = 5) -> None:
        if int(max_restarts) < 1:
            raise ValueError("max_restarts must be >= 1")
        self.selector = selector
        self.max_restarts = int(max_restarts)

    def object_ref(self) -> list[str]:
        return ["pods", "-l", self.selector]

    def pod_ref(self) -> list[str]:
        return ["-l", self.selector]

    async def check(self, provider: Provider) -> ProbeResult:
        r = await provider.run(["get", "pods", "-l", self.selector, "-o", "json"], timeout=30)
        if not r.ok:
            return ProbeResult(False, f"kubectl get pods failed: {r.stderr.strip()}")
        try:
            items = json.loads(r.stdout).get("items", [])
        except json.JSONDecodeError as exc:
            return ProbeResult(False, f"could not parse kubectl json: {exc}")
        if not items:
            return ProbeResult(True, f"no pods match {self.selector!r}")

        worst_restarts = -1
        reason = ""
        for pod in items:
            pod_name = pod.get("metadata", {}).get("name", "?")
            for cs in pod.get("status", {}).get("containerStatuses", []):
                if not isinstance(cs, dict):
                    continue
                restarts = int(cs.get("restartCount", 0) or 0)
                why = _crash_reason(cs)
                if why:  # CrashLoopBackOff / OOMKilled trumps a raw count
                    return ProbeResult(False, f"{pod_name}/{cs.get('name', '?')}: {why}")
                if restarts > worst_restarts:
                    worst_restarts = restarts
                    reason = f"{pod_name}/{cs.get('name', '?')} restarted {restarts}x"

        if worst_restarts >= self.max_restarts:
            return ProbeResult(False, f"{reason} (>= {self.max_restarts})")
        return ProbeResult(True, f"{len(items)} pod(s), worst {max(worst_restarts, 0)} restarts")


def _crash_reason(cs: dict[str, object]) -> str:
    """A crash signal for a container status: CrashLoopBackOff or OOMKilled, else ''."""
    state = cs.get("state")
    if isinstance(state, dict):
        waiting = state.get("waiting")
        if isinstance(waiting, dict) and waiting.get("reason") == "CrashLoopBackOff":
            return "CrashLoopBackOff"
    last = cs.get("lastState")
    if isinstance(last, dict):
        term = last.get("terminated")
        if isinstance(term, dict) and term.get("reason") == "OOMKilled":
            return "OOMKilled"
    return ""


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
