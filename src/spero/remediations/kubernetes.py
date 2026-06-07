# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# __creation__ = 2026-06-03
# __author__ = "jndjama (Joy Ndjama)"
# __copyright__ = "Copyright 2026 ALTIKVA."
# __licence__ = "MIT & CC BY-NC-SA (https://www.altikva.com/licenses/LICENSE-1.0)"
# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# Description: Kubernetes remediations: rollout restart, scale, delete pod.

"""Kubernetes remediations: rollout restart, scale, delete pod.

Each issues a kubectl subcommand through the provider (which supplies the
kubectl/context/namespace prefix).
"""

from __future__ import annotations

from typing import ClassVar

from spero.providers.base import Provider
from spero.remediations.base import Remediation, RemediationResult


class RolloutRestart(Remediation):
    """`kubectl rollout restart deployment/<name>` -- the graceful k8s heal."""

    type: ClassVar[str] = "rollout-restart"

    def __init__(self, deployment: str) -> None:
        self.deployment = deployment

    async def apply(self, provider: Provider) -> RemediationResult:
        r = await provider.run(["rollout", "restart", f"deployment/{self.deployment}"], timeout=60)
        return RemediationResult(r.ok, r.stderr.strip() or f"rollout restart {self.deployment}")


class ScaleDeployment(Remediation):
    """`kubectl scale deployment/<name> --replicas=N`."""

    type: ClassVar[str] = "scale"

    def __init__(self, deployment: str, replicas: int) -> None:
        self.deployment = deployment
        self.replicas = int(replicas)

    async def apply(self, provider: Provider) -> RemediationResult:
        r = await provider.run(
            ["scale", f"deployment/{self.deployment}", f"--replicas={self.replicas}"], timeout=60
        )
        return RemediationResult(
            r.ok, r.stderr.strip() or f"scaled {self.deployment} to {self.replicas}"
        )


class PatchRequests(Remediation):
    """`kubectl set resources deployment/<name> --requests=...` -- rightsizing.

    Closes the loop the ``resource-usage`` probe opens: when a pod runs hot against
    its declared requests, raise (or lower) them. Marked destructive because it
    mutates the workload spec and triggers a rolling restart, so it may never run
    unattended -- autonomy ``auto`` is rejected at policy load, and a human or the
    AI approver always gates it. At least one of ``cpu``/``memory`` is required.
    """

    type: ClassVar[str] = "patch-requests"
    destructive: ClassVar[bool] = True

    def __init__(
        self,
        deployment: str,
        cpu: str | None = None,
        memory: str | None = None,
        container: str | None = None,
    ) -> None:
        if not cpu and not memory:
            raise ValueError("patch-requests needs at least one of cpu/memory")
        self.deployment = deployment
        self.cpu = str(cpu) if cpu else None
        self.memory = str(memory) if memory else None
        self.container = container

    async def apply(self, provider: Provider) -> RemediationResult:
        requests = ",".join(
            f"{k}={v}" for k, v in (("cpu", self.cpu), ("memory", self.memory)) if v
        )
        cmd = ["set", "resources", f"deployment/{self.deployment}", f"--requests={requests}"]
        if self.container:
            cmd += ["-c", self.container]
        r = await provider.run(cmd, timeout=60)
        return RemediationResult(
            r.ok, r.stderr.strip() or f"set requests {requests} on {self.deployment}"
        )


class DeletePod(Remediation):
    """`kubectl delete pod -l <selector>` -- forceful; let the controller recreate."""

    type: ClassVar[str] = "delete-pod"
    destructive: ClassVar[bool] = True

    def __init__(self, selector: str) -> None:
        self.selector = selector

    async def apply(self, provider: Provider) -> RemediationResult:
        r = await provider.run(["delete", "pod", "-l", self.selector], timeout=60)
        return RemediationResult(
            r.ok, r.stderr.strip() or f"deleted pods matching {self.selector!r}"
        )
