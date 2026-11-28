# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# __creation__ = 2026-06-03
# __author__ = "jndjama (Joy Ndjama)"
# __copyright__ = "Copyright 2026 ALTIKVA."
# __licence__ = "Apache-2.0 (https://www.apache.org/licenses/LICENSE-2.0)"
# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# Description: Host probes: process, systemd, port, disk.

"""Host probes: process, systemd, port, disk.

Each probe is read-only and speaks to the target only through ``provider.run``,
using argv-style commands (no shell): ``pgrep`` / ``systemctl is-active`` /
``ss`` or ``netstat`` / ``df``, never a ``ps | awk`` pipeline or a grep over localized output.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import ClassVar

from spero.probes.base import Probe, ProbeResult
from spero.providers.base import Provider
from spero.providers.command import NOT_FOUND_RC


class ProcessProbe(Probe):
    """Healthy iff at least one process matches."""

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
    """Healthy iff ``systemctl is-active`` reports active."""

    type: ClassVar[str] = "systemd"

    def __init__(self, unit: str) -> None:
        self.unit = unit

    async def check(self, provider: Provider) -> ProbeResult:
        r = await provider.run(["systemctl", "is-active", self.unit], timeout=15)
        state = r.stdout.strip() or r.stderr.strip()
        return ProbeResult(r.ok, f"{self.unit} is {state or 'unknown'}")


class PortProbe(Probe):
    """Healthy iff something is listening on the TCP port.

    Asks ``ss -ltnH`` and falls back to ``netstat -an`` where ``ss`` is missing
    (macOS, BSD, minimal Linux images). ``netstat`` lists every listening socket
    without privileges on both macOS and Linux, unlike ``lsof``, which only shows
    the calling user's processes. The tool that answered is remembered, so later
    checks go straight to it. When neither exists the result says the sockets
    could not be queried, which is not the same as "nothing listening".
    """

    type: ClassVar[str] = "port"

    def __init__(self, port: int, host: str | None = None) -> None:
        self.port = int(port)
        self.host = host
        self._tool: _SocketTool | None = None

    async def check(self, provider: Provider) -> ProbeResult:
        tools = [self._tool] if self._tool is not None else list(_SOCKET_TOOLS)
        for tool in tools:
            r = await provider.run(list(tool.argv), timeout=15)
            if r.returncode == NOT_FOUND_RC:
                continue
            if not r.ok:
                return ProbeResult(
                    False, f"could not query listening sockets with {tool.name}: {r.stderr.strip()}"
                )
            self._tool = tool
            if tool.listening_on(r.stdout, self.port, self.host):
                return ProbeResult(True, f"listening on port {self.port}")
            return ProbeResult(False, f"nothing listening on port {self.port}")
        self._tool = None
        names = " or ".join(t.name for t in _SOCKET_TOOLS)
        return ProbeResult(
            False, f"cannot query listening sockets: {names} not found on the target"
        )


class DiskProbe(Probe):
    """Healthy iff filesystem usage at ``path`` is at or below ``threshold_pct``.

    Measures filesystem usage, not hardware health. This is the probe the
    predictive layer forecasts against.
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


def _bind_matches(bind: str, host: str | None) -> bool:
    return host is None or bind in (host, "*", "0.0.0.0", "[::]", "::")


def _listening_on(ss_output: str, port: int, host: str | None) -> bool:
    """Scan `ss -ltnH` output for a listening socket on the given port."""
    suffix = f":{port}"
    for line in ss_output.splitlines():
        cols = line.split()
        if len(cols) < 4:
            continue
        local = cols[3]  # Local Address:Port
        if local.endswith(suffix) and _bind_matches(local[: -len(suffix)], host):
            return True
    return False


def _listening_on_netstat(netstat_output: str, port: int, host: str | None) -> bool:
    """Scan `netstat -an` output for a TCP socket in LISTEN state on the given port.

    Linux writes the local address as ``0.0.0.0:8080`` or ``:::8080``; macOS and
    the BSDs write ``*.8080``, ``127.0.0.1.8080`` or ``::1.8080``.
    """
    for line in netstat_output.splitlines():
        cols = line.split()
        if len(cols) < 6 or not cols[0].startswith("tcp") or cols[-1] != "LISTEN":
            continue
        local = cols[3]
        cut = max(local.rfind(":"), local.rfind("."))
        if cut < 0 or local[cut + 1 :] != str(port):
            continue
        if _bind_matches(local[:cut], host):
            return True
    return False


@dataclass(frozen=True, slots=True)
class _SocketTool:
    name: str
    argv: tuple[str, ...]
    listening_on: Callable[[str, int, str | None], bool]


_SOCKET_TOOLS: tuple[_SocketTool, ...] = (
    _SocketTool("ss", ("ss", "-ltnH"), _listening_on),
    _SocketTool("netstat", ("netstat", "-an"), _listening_on_netstat),
)


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
