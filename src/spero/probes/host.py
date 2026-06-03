"""Host probes: process, systemd, port, disk.

Each probe is read-only and speaks to the target only through ``provider.run``,
using argv-style commands (no shell), reimplementing the legacy bot's
``ps | awk`` / locale-grep pipelines as ``pgrep`` / ``systemctl is-active`` /
``ss`` / ``df``.
"""

from __future__ import annotations

from typing import ClassVar

from spero.probes.base import Probe, ProbeResult
from spero.providers.base import Provider


class ProcessProbe(Probe):
    """Healthy iff at least one process matches. Ports get_process_pid."""

    type: ClassVar[str] = "process"

    def __init__(self, name: str, user: str | None = None) -> None:
        self.pattern = name
        self.user = user

    async def check(self, provider: Provider) -> ProbeResult:
        cmd = ["pgrep", "-f"]
        if self.user:
            cmd = ["pgrep", "-u", self.user, "-f"]
        cmd.append(self.pattern)
        r = await provider.run(cmd, timeout=15)
        if r.ok:
            pids = r.stdout.split()
            return ProbeResult(True, f"{len(pids)} process(es) matching {self.pattern!r}")
        return ProbeResult(False, f"no process matching {self.pattern!r}")


class SystemdProbe(Probe):
    """Healthy iff ``systemctl is-active`` reports active. Ports is_service_running."""

    type: ClassVar[str] = "systemd"

    def __init__(self, unit: str) -> None:
        self.unit = unit

    async def check(self, provider: Provider) -> ProbeResult:
        r = await provider.run(["systemctl", "is-active", self.unit], timeout=15)
        state = r.stdout.strip() or r.stderr.strip()
        return ProbeResult(r.ok, f"{self.unit} is {state or 'unknown'}")


class PortProbe(Probe):
    """Healthy iff something is listening on the TCP port. Ports is_port_used (lsof)."""

    type: ClassVar[str] = "port"

    def __init__(self, port: int, host: str | None = None) -> None:
        self.port = int(port)
        self.host = host

    async def check(self, provider: Provider) -> ProbeResult:
        r = await provider.run(["ss", "-ltnH"], timeout=15)
        if not r.ok:
            return ProbeResult(False, f"could not query listening sockets: {r.stderr.strip()}")
        listening = _listening_on(r.stdout, self.port, self.host)
        if listening:
            return ProbeResult(True, f"listening on port {self.port}")
        return ProbeResult(False, f"nothing listening on port {self.port}")


class DiskProbe(Probe):
    """Healthy iff filesystem usage at ``path`` is at or below ``threshold_pct``.

    New in Spero (the legacy disk check was RAID hardware health). This is the
    probe the Phase 3 predictive layer forecasts against.
    """

    type: ClassVar[str] = "disk"

    def __init__(self, path: str, threshold_pct: int = 90) -> None:
        self.path = path
        self.threshold_pct = int(threshold_pct)

    async def check(self, provider: Provider) -> ProbeResult:
        r = await provider.run(["df", "-P", self.path], timeout=15)
        if not r.ok:
            return ProbeResult(False, f"df failed for {self.path}: {r.stderr.strip()}")
        used = _parse_df_use_pct(r.stdout)
        if used is None:
            return ProbeResult(False, f"could not parse df output for {self.path}")
        healthy = used <= self.threshold_pct
        return ProbeResult(healthy, f"{self.path} at {used}% (threshold {self.threshold_pct}%)")


def _listening_on(ss_output: str, port: int, host: str | None) -> bool:
    """Scan `ss -ltnH` output for a listening socket on the given port."""
    suffix = f":{port}"
    for line in ss_output.splitlines():
        cols = line.split()
        if len(cols) < 4:
            continue
        local = cols[3]  # Local Address:Port
        if not local.endswith(suffix):
            continue
        if host is not None:
            bind = local[: -len(suffix)]
            if bind not in (host, "*", "0.0.0.0", "[::]", "::"):
                continue
        return True
    return False


def _parse_df_use_pct(df_output: str) -> int | None:
    """Pull the use percentage from `df -P` output (last row, second-to-last col)."""
    lines = [ln for ln in df_output.splitlines() if ln.strip()]
    if len(lines) < 2:
        return None
    cols = lines[-1].split()
    for col in reversed(cols):
        if col.endswith("%") and col[:-1].isdigit():
            return int(col[:-1])
    return None
