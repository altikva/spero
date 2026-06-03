"""Remediations: WHAT Spero does to heal a target, plus a registry to build from policy."""

from __future__ import annotations

from spero.core.models import RemediationSpec
from spero.remediations.base import Remediation, RemediationResult
from spero.remediations.host import KillProcess, RespawnProcess, RestartService, RotateLogs

REMEDIATIONS: dict[str, type[Remediation]] = {
    cls.type: cls for cls in (RestartService, RespawnProcess, KillProcess, RotateLogs)
}


def build_remediation(spec: RemediationSpec) -> Remediation:
    """Construct a Remediation action from a policy RemediationSpec."""
    try:
        cls = REMEDIATIONS[spec.type]
    except KeyError:
        raise ValueError(
            f"unknown remediation type: {spec.type!r} (have {sorted(REMEDIATIONS)})"
        ) from None
    return cls(**spec.params)


__all__ = [
    "REMEDIATIONS",
    "KillProcess",
    "Remediation",
    "RemediationResult",
    "RespawnProcess",
    "RestartService",
    "RotateLogs",
    "build_remediation",
]
