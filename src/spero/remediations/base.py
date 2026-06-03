"""The Remediation interface: a healing action, governed by an autonomy level."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import ClassVar

from spero.core.models import Autonomy
from spero.providers.base import Provider


@dataclass(slots=True)
class RemediationResult:
    success: bool
    detail: str = ""


class Remediation(ABC):
    """An action that brings a target back to health (restart, respawn, rotate, ...).

    ``autonomy`` decides whether it may run unattended; the engine consults it
    before applying. High-risk actions default to requiring a human.
    """

    type: ClassVar[str] = ""
    autonomy: ClassVar[Autonomy] = Autonomy.suggest

    @abstractmethod
    def apply(self, provider: Provider) -> RemediationResult:
        raise NotImplementedError
