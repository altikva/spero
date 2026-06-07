# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# __creation__ = 2026-06-05
# __author__ = "jndjama (Joy Ndjama)"
# __copyright__ = "Copyright 2026 ALTIKVA."
# __licence__ = "MIT & CC BY-NC-SA (https://www.altikva.com/licenses/LICENSE-1.0)"
# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# Description: ResourceUsageProbe -- flag pods whose live CPU/memory usage runs hot
#              against their declared requests (metrics-server backed rightsizing signal).

"""Resource-usage probe: are matching pods running hot against their requests?

Reads live usage from metrics-server (``kubectl top pod``) and declared requests
(``kubectl get pod -o json``), then flags any pod whose CPU or memory usage exceeds
a configurable percentage of what it requested. This is the read-only, high-signal
half of rightsizing: it surfaces "this pod is starved / about to OOM" without
mutating anything. Acting on it (patching requests, or applying a VPA recommendation)
is a separate remediation, gated by the autonomy model -- spero governs the change,
it does not reimplement an autoscaler.

A pod with no request set for a resource is skipped for that resource: you cannot be
"over" a request that does not exist (that absence is its own rightsizing finding, for
a future probe). Requires metrics-server in the cluster.
"""

from __future__ import annotations

import json
from typing import ClassVar

from spero.probes.base import Probe, ProbeResult
from spero.providers.base import Provider


class ResourceUsageProbe(Probe):
    """Unhealthy if any pod matching ``selector`` uses >= the threshold % of its request."""

    type: ClassVar[str] = "resource-usage"

    def __init__(
        self, selector: str, cpu_threshold_pct: float = 90, mem_threshold_pct: float = 90
    ) -> None:
        self.selector = selector
        self.cpu_threshold = float(cpu_threshold_pct)
        self.mem_threshold = float(mem_threshold_pct)

    def object_ref(self) -> list[str]:
        return ["pods", "-l", self.selector]

    def pod_ref(self) -> list[str]:
        return ["-l", self.selector]

    async def check(self, provider: Provider) -> ProbeResult:
        top = await provider.run(["top", "pod", "-l", self.selector, "--no-headers"], timeout=30)
        if not top.ok:
            return ProbeResult(False, f"kubectl top failed: {top.stderr.strip()}")
        usage = _parse_top(top.stdout)
        if not usage:
            return ProbeResult(True, f"no pods match {self.selector!r}")

        spec = await provider.run(["get", "pods", "-l", self.selector, "-o", "json"], timeout=30)
        if not spec.ok:
            return ProbeResult(False, f"kubectl get pods failed: {spec.stderr.strip()}")
        try:
            requests = _parse_requests(spec.stdout)
        except json.JSONDecodeError as exc:
            return ProbeResult(False, f"could not parse kubectl json: {exc}")

        worst_pct = -1.0
        worst_detail = ""
        for pod, (cpu_u, mem_u) in usage.items():
            cpu_r, mem_r = requests.get(pod, (None, None))
            for label, used, req, thr in (
                ("cpu", cpu_u, cpu_r, self.cpu_threshold),
                ("mem", mem_u, mem_r, self.mem_threshold),
            ):
                if req:  # request declared and non-zero
                    pct = used / req * 100
                    if pct >= thr and pct > worst_pct:
                        worst_pct = pct
                        worst_detail = f"{pod} {label} at {pct:.0f}% of request (>= {thr:.0f}%)"

        if worst_detail:
            return ProbeResult(False, f"over threshold: {worst_detail}")
        return ProbeResult(True, f"{len(usage)} pod(s) within request thresholds")


def _parse_top(stdout: str) -> dict[str, tuple[float, float]]:
    """Parse `kubectl top pod --no-headers` lines into {pod: (cpu_millicores, mem_bytes)}."""
    out: dict[str, tuple[float, float]] = {}
    for line in stdout.splitlines():
        parts = line.split()
        if len(parts) >= 3:
            out[parts[0]] = (_cpu_to_millicores(parts[1]), _mem_to_bytes(parts[2]))
    return out


def _parse_requests(stdout: str) -> dict[str, tuple[float | None, float | None]]:
    """Sum each pod's container CPU/memory requests into {pod: (cpu_m|None, mem_bytes|None)}."""
    out: dict[str, tuple[float | None, float | None]] = {}
    for item in json.loads(stdout).get("items", []):
        name = item.get("metadata", {}).get("name", "")
        cpu: float | None = None
        mem: float | None = None
        for container in item.get("spec", {}).get("containers", []):
            req = container.get("resources", {}).get("requests", {})
            if "cpu" in req:
                cpu = (cpu or 0.0) + _cpu_to_millicores(str(req["cpu"]))
            if "memory" in req:
                mem = (mem or 0.0) + _mem_to_bytes(str(req["memory"]))
        out[name] = (cpu, mem)
    return out


def _cpu_to_millicores(value: str) -> float:
    """'250m' -> 250; '2' -> 2000; '1500m' -> 1500."""
    value = value.strip()
    if value.endswith("m"):
        return float(value[:-1])
    return float(value) * 1000


_MEM_UNITS = {
    "Ki": 2**10,
    "Mi": 2**20,
    "Gi": 2**30,
    "Ti": 2**40,
    "K": 1e3,
    "M": 1e6,
    "G": 1e9,
    "T": 1e12,
}


def _mem_to_bytes(value: str) -> float:
    """'64Mi' -> 67108864; '1Gi' -> 1073741824; '512000' -> 512000."""
    value = value.strip()
    for suffix, factor in _MEM_UNITS.items():
        if value.endswith(suffix):
            return float(value[: -len(suffix)]) * factor
    return float(value)
