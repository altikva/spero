# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# __creation__ = 2026-06-03
# __author__ = "jndjama (Joy Ndjama)"
# __copyright__ = "Copyright 2026 ALTIKVA."
# __licence__ = "MIT & CC BY-NC-SA (http://www.altikva.com/licenses/LICENSE-1.0)"
# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#

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
    # Destructive actions (data loss / forceful kill) may never run unattended:
    # the policy validator forbids autonomy=auto for them, so they always need a
    # gate (a human, or the AI approver under --ai-approve).
    destructive: ClassVar[bool] = False

    @abstractmethod
    async def apply(self, provider: Provider) -> RemediationResult:
        raise NotImplementedError
