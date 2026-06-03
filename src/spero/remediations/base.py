"""The Remediation interface: a healing action, governed by an autonomy level."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import ClassVar

from spero.providers.base import Provider


@dataclass(slots=True)
class RemediationResult:
    success: bool
    detail: str = ""


class Remediation(ABC):
    """An action that brings a target back to health (restart, respawn, rotate, ...).

    Whether it may run unattended is decided by the engine from the policy's
    ``RemediationSpec.autonomy`` -- the action itself just performs the work.
    """

    type: ClassVar[str] = ""

    @abstractmethod
    async def apply(self, provider: Provider) -> RemediationResult:
        raise NotImplementedError
