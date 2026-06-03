"""Host remediations: restart a service, respawn a process, kill, rotate logs.

Argv-style, no shell. The "start command" that used to live in the bot's
TeleAction DB rows now comes from policy params.
"""

from __future__ import annotations

import shlex
from typing import ClassVar

from spero.providers.base import Provider
from spero.remediations.base import Remediation, RemediationResult


class RestartService(Remediation):
    """`systemctl restart <unit>`. Ports action_over_service."""

    type: ClassVar[str] = "restart"

    def __init__(self, unit: str, sudo: bool = False) -> None:
        self.unit = unit
        self.sudo = sudo

    async def apply(self, provider: Provider) -> RemediationResult:
        cmd = ["systemctl", "restart", self.unit]
        if self.sudo:
            cmd = ["sudo", *cmd]
        r = await provider.run(cmd, timeout=60)
        return RemediationResult(r.ok, r.stderr.strip() or f"restarted {self.unit}")


class RespawnProcess(Remediation):
    """Run a start command, optionally as another user. Ports start_stop_process."""

    type: ClassVar[str] = "respawn"

    def __init__(self, start: str, user: str | None = None) -> None:
        self.start = start
        self.user = user

    async def apply(self, provider: Provider) -> RemediationResult:
        if self.user:
            cmd = ["su", "-", self.user, "-c", self.start]
        else:
            cmd = shlex.split(self.start)
        r = await provider.run(cmd, timeout=60)
        return RemediationResult(r.ok, r.stderr.strip() or f"started {self.start!r}")


class KillProcess(Remediation):
    """`pkill -9` matching processes. Ports do_kill_processes; the forceful step."""

    type: ClassVar[str] = "kill"

    def __init__(self, name: str, user: str | None = None, signal: int = 9) -> None:
        self.pattern = name
        self.user = user
        self.signal = int(signal)

    async def apply(self, provider: Provider) -> RemediationResult:
        cmd = ["pkill", f"-{self.signal}", "-f"]
        if self.user:
            cmd = ["pkill", f"-{self.signal}", "-u", self.user, "-f"]
        cmd.append(self.pattern)
        r = await provider.run(cmd, timeout=30)
        # pkill exits 1 when nothing matched; treat that as "already gone", a success.
        ok = r.returncode in (0, 1)
        return RemediationResult(ok, f"signalled {self.pattern!r} (rc={r.returncode})")


class RotateLogs(Remediation):
    """Delete files older than ``keep_days`` under ``path`` to free disk.

    Destructive, so policies should default this to ``suggest`` autonomy.
    """

    type: ClassVar[str] = "rotate"

    def __init__(self, path: str, keep_days: int = 21) -> None:
        self.path = path
        self.keep_days = int(keep_days)

    async def apply(self, provider: Provider) -> RemediationResult:
        cmd = ["find", self.path, "-type", "f", "-mtime", f"+{self.keep_days}", "-delete"]
        r = await provider.run(cmd, timeout=120)
        return RemediationResult(
            r.ok, r.stderr.strip() or f"pruned files older than {self.keep_days}d in {self.path}"
        )
