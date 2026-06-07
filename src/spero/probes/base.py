# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# __creation__ = 2026-06-03
# __author__ = "jndjama (Joy Ndjama)"
# __copyright__ = "Copyright 2026 ALTIKVA."
# __licence__ = "MIT & CC BY-NC-SA (https://www.altikva.com/licenses/LICENSE-1.0)"
# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# Description: The Probe interface: ask a provider whether a target is healthy.

"""The Probe interface: ask a provider whether a target is healthy."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import ClassVar

from spero.providers.base import Provider


@dataclass(slots=True)
class ProbeResult:
    healthy: bool
    detail: str = ""


class Probe(ABC):
    """Checks one target's health through a provider.

    Host probes (process, systemd, port, disk, http) land in Phase 1; the
    Kubernetes probes (pod-ready, restart-count, OOMKilled, PVC-usage) in Phase 2.
    """

    type: ClassVar[str] = ""

    @abstractmethod
    async def check(self, provider: Provider) -> ProbeResult:
        raise NotImplementedError

    def object_ref(self) -> list[str] | None:
        """kubectl args naming the underlying object(s), for `get <ref> -o yaml`.

        Returns None when there is no single inspectable Kubernetes object (host and
        data-infra probes). Used by `spero top` to show a target's YAML on demand.
        """
        return None

    def pod_ref(self) -> list[str] | None:
        """kubectl reference to the target's pod(s): a ``-l <selector>`` pair or a
        ``<kind>/<name>`` workload that resolves to pods.

        Shared by the log view (`kubectl logs <ref>`) and the local exec convenience
        (`kubectl exec -it <pod>`). Returns None when the target has no pods to stream
        or shell into: host/data-infra probes, and CRDs (KEDA, elpio) whose backing
        workload is not directly addressable from the probe spec alone.
        """
        return None
