# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# __creation__ = 2026-06-03
# __author__ = "jndjama (Joy Ndjama)"
# __copyright__ = "Copyright 2026 ALTIKVA."
# __licence__ = "MIT & CC BY-NC-SA (http://www.altikva.com/licenses/LICENSE-1.0)"
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
