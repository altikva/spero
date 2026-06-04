# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# __creation__ = 2026-06-03
# __author__ = "jndjama (Joy Ndjama)"
# __copyright__ = "Copyright 2026 ALTIKVA."
# __licence__ = "MIT & CC BY-NC-SA (http://www.altikva.com/licenses/LICENSE-1.0)"
# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#

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
