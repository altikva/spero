# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# __creation__ = 2026-06-03
# __author__ = "jndjama (Joy Ndjama)"
# __copyright__ = "Copyright 2026 ALTIKVA."
# __licence__ = "MIT & CC BY-NC-SA (https://www.altikva.com/licenses/LICENSE-1.0)"
# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# Description: Remediations: WHAT Spero does to heal a target, plus a registry to build from policy.

"""Remediations: WHAT Spero does to heal a target, plus a registry to build from policy."""

from __future__ import annotations

from spero.core.models import RemediationSpec
from spero.remediations.base import Remediation, RemediationResult
from spero.remediations.host import KillProcess, RespawnProcess, RestartService, RotateLogs
from spero.remediations.keda import UnpauseScaledObject  # EXPERIMENTAL: a4c serverless seam spike
from spero.remediations.kubernetes import DeletePod, RolloutRestart, ScaleDeployment

REMEDIATIONS: dict[str, type[Remediation]] = {
    cls.type: cls
    for cls in (
        RestartService,
        RespawnProcess,
        KillProcess,
        RotateLogs,
        RolloutRestart,
        ScaleDeployment,
        DeletePod,
        UnpauseScaledObject,
    )
}


def build_remediation(spec: RemediationSpec) -> Remediation:
    """Construct a Remediation action from a policy RemediationSpec."""
    try:
        cls = REMEDIATIONS[spec.type]
    except KeyError:
        raise ValueError(
            f"unknown remediation type: {spec.type!r} (have {sorted(REMEDIATIONS)})"
        ) from None
    try:
        return cls(**spec.params)
    except TypeError as exc:
        raise ValueError(f"bad params for remediation {spec.type!r}: {exc}") from exc


__all__ = [
    "REMEDIATIONS",
    "DeletePod",
    "KillProcess",
    "Remediation",
    "RemediationResult",
    "RespawnProcess",
    "RestartService",
    "RolloutRestart",
    "RotateLogs",
    "ScaleDeployment",
    "UnpauseScaledObject",
    "build_remediation",
]
