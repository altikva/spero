# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# __creation__ = 2026-06-03
# __author__ = "jndjama (Joy Ndjama)"
# __copyright__ = "Copyright 2026 ALTIKVA."
# __licence__ = "Apache-2.0 (https://www.apache.org/licenses/LICENSE-2.0)"
# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# Description: Host remediations: restart a service, respawn a process, kill, rotate logs.

"""Host remediations: restart a service, respawn a process, kill, rotate logs.

Argv-style, no shell. The command that starts a process comes from policy
params, not from a database.
"""

from __future__ import annotations

import shlex
from collections.abc import Mapping
from typing import ClassVar

from spero.providers.base import Provider
from spero.remediations.base import Remediation, RemediationResult


class RestartService(Remediation):
    """`systemctl restart <unit>`."""

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
    """Run a start command, optionally as another user.

    ``start`` is tokenized argv-style (``shlex.split``), never handed to a shell --
    so policy params can't smuggle in ``;``/``$(...)``/redirection. If you genuinely
    need shell features, make the start command explicit, e.g. ``sh -c "a && b"``.
    Running as another user goes through ``runuser -u <user> --`` (argv, no shell),
    not ``su -c`` (which would shell-interpret the command).

    ``env`` sets variables for the started process: merged onto the provider's
    environment, or the whole environment when ``env_replace`` is true (then
    ``start`` should be an absolute path, or ``env`` should carry ``PATH``).
    Values may be secrets: results and logs name the keys only, never the values.
    """

    type: ClassVar[str] = "respawn"

    def __init__(
        self,
        start: str,
        user: str | None = None,
        env: Mapping[str, str] | None = None,
        env_replace: bool = False,
    ) -> None:
        if env is not None and (
            not isinstance(env, Mapping)
            or not all(isinstance(k, str) and isinstance(v, str) for k, v in env.items())
        ):
            # TypeError so build_remediation reports it as bad params at policy load.
            raise TypeError("env must be a mapping of strings to strings")
        if not isinstance(env_replace, bool):
            raise TypeError("env_replace must be a boolean")
        if env_replace and env is None:
            raise TypeError("env_replace needs env (the variables to start with)")
        self.start = start
        self.user = user
        self.env = dict(env) if env is not None else None
        self.env_replace = env_replace

    async def apply(self, provider: Provider) -> RemediationResult:
        argv = shlex.split(self.start)
        cmd = ["runuser", "-u", self.user, "--", *argv] if self.user else argv
        r = await provider.run(cmd, timeout=60, env=self.env, env_replace=self.env_replace)
        detail = f"started {self.start!r}"
        if self.env is not None:
            mode = "replaced" if self.env_replace else "merged"
            keys = ", ".join(sorted(self.env)) or "none"
            detail += f" (env {mode}: {keys})"
        return RemediationResult(r.ok, r.stderr.strip() or detail)


class KillProcess(Remediation):
    """`pkill -9` matching processes; the forceful step."""

    type: ClassVar[str] = "kill"
    destructive: ClassVar[bool] = True

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
    destructive: ClassVar[bool] = True

    def __init__(self, path: str, keep_days: int = 21) -> None:
        self.path = path
        self.keep_days = int(keep_days)

    async def apply(self, provider: Provider) -> RemediationResult:
        cmd = ["find", self.path, "-type", "f", "-mtime", f"+{self.keep_days}", "-delete"]
        r = await provider.run(cmd, timeout=120)
        return RemediationResult(
            r.ok, r.stderr.strip() or f"pruned files older than {self.keep_days}d in {self.path}"
        )
