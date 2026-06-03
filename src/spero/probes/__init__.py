"""Probes: HOW you know a target is healthy, plus a registry to build from policy."""

from __future__ import annotations

from spero.core.models import ProbeSpec
from spero.probes.base import Probe, ProbeResult
from spero.probes.host import DiskProbe, PortProbe, ProcessProbe, SystemdProbe

PROBES: dict[str, type[Probe]] = {
    cls.type: cls for cls in (ProcessProbe, SystemdProbe, PortProbe, DiskProbe)
}


def build_probe(spec: ProbeSpec) -> Probe:
    """Construct a Probe from a policy ProbeSpec."""
    try:
        cls = PROBES[spec.type]
    except KeyError:
        raise ValueError(f"unknown probe type: {spec.type!r} (have {sorted(PROBES)})") from None
    try:
        return cls(**spec.params)
    except TypeError as exc:
        raise ValueError(f"bad params for probe {spec.type!r}: {exc}") from exc


__all__ = [
    "PROBES",
    "DiskProbe",
    "PortProbe",
    "Probe",
    "ProbeResult",
    "ProcessProbe",
    "SystemdProbe",
    "build_probe",
]
