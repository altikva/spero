"""The Probe interface: ask a provider whether a target is healthy."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

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

    type: str

    @abstractmethod
    def check(self, provider: Provider) -> ProbeResult:
        raise NotImplementedError
