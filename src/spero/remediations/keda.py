# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# __creation__ = 2026-06-04
# __author__ = "jndjama (Joy Ndjama)"
# __copyright__ = "Copyright 2026 ALTIKVA."
# __licence__ = "MIT & CC BY-NC-SA (https://www.altikva.com/licenses/LICENSE-1.0)"
# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# Description: KEDA ScaledObject remediation -- the healing half of the a4c serverless seam
#              experiment.

"""KEDA ScaledObject remediation -- the healing half of the a4c serverless seam experiment.

EXPERIMENTAL (see docs/experiments/0001-keda-seam.md).

This deliberately implements the *healing* shape, not the *provisioning* shape. A
ScaledObject that someone left paused (KEDA's ``autoscaling.keda.sh/paused`` /
``paused-replicas`` annotations freeze autoscaling) is a real, recoverable failure
of an EXISTING resource -- which is exactly what spero's Remediation seam is for, and
it fits with no friction. Creating a ScaledObject that does not exist yet is
provisioning, needs a rendered manifest fed over stdin, and does NOT fit the current
``Provider.run`` argv-only seam. That gap is the experiment's key finding; it is
documented, not faked here.
"""

from __future__ import annotations

from typing import ClassVar

from spero.providers.base import Provider
from spero.remediations.base import Remediation, RemediationResult

# KEDA freezes autoscaling when either annotation is present; clearing both resumes it.
_PAUSE_ANNOTATIONS = ("autoscaling.keda.sh/paused", "autoscaling.keda.sh/paused-replicas")


class UnpauseScaledObject(Remediation):
    """Resume a paused KEDA ScaledObject by clearing its pause annotations.

    ``kubectl annotate scaledobject/<name> <ann>- ... --overwrite`` (a trailing ``-``
    removes the annotation). Idempotent: clearing an absent annotation is a no-op
    success, so re-running while the target recovers is safe.
    """

    type: ClassVar[str] = "keda-unpause"

    def __init__(self, name: str) -> None:
        self.name = name

    async def apply(self, provider: Provider) -> RemediationResult:
        removals = [f"{ann}-" for ann in _PAUSE_ANNOTATIONS]
        r = await provider.run(
            ["annotate", f"scaledobject/{self.name}", *removals, "--overwrite"], timeout=60
        )
        return RemediationResult(r.ok, r.stderr.strip() or f"unpaused scaledobject/{self.name}")
