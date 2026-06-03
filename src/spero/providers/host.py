"""Host providers: run commands locally or over SSH.

``LocalProvider`` runs on the machine Spero lives on. ``SSHProvider`` shells out
to ``ssh`` for now (faithful to the original bot); a paramiko/asyncssh transport
is a Phase 1 follow-up. Both share the local executor in :mod:`spero.providers.command`.
"""

from __future__ import annotations

import shlex
from collections.abc import Mapping, Sequence

from spero.providers.base import Provider
from spero.providers.command import CommandResult, run_local

# Non-interactive, fail-fast SSH defaults. Replaces the bot's free-form SSH_OPTS.
DEFAULT_SSH_OPTS: tuple[str, ...] = (
    "-o",
    "BatchMode=yes",
    "-o",
    "StrictHostKeyChecking=accept-new",
    "-o",
    "ConnectTimeout=10",
)


class LocalProvider(Provider):
    name = "local"

    def run(
        self,
        command: str | Sequence[str],
        *,
        timeout: float | None = None,
        retries: int = 0,
        cwd: str | None = None,
        env: Mapping[str, str] | None = None,
    ) -> CommandResult:
        return run_local(command, timeout=timeout, retries=retries, cwd=cwd, env=env)


class SSHProvider(Provider):
    name = "ssh"

    def __init__(
        self,
        host: str,
        *,
        user: str | None = None,
        ssh_opts: Sequence[str] = DEFAULT_SSH_OPTS,
        ssh_bin: str = "ssh",
    ) -> None:
        self.host = host
        self.user = user
        self.ssh_opts = tuple(ssh_opts)
        self.ssh_bin = ssh_bin

    @property
    def destination(self) -> str:
        return f"{self.user}@{self.host}" if self.user else self.host

    def build_argv(self, command: str | Sequence[str]) -> list[str]:
        """Build the local ``ssh`` argument vector for a remote command."""
        remote = command if isinstance(command, str) else shlex.join(command)
        return [self.ssh_bin, *self.ssh_opts, self.destination, remote]

    def run(
        self,
        command: str | Sequence[str],
        *,
        timeout: float | None = None,
        retries: int = 0,
        cwd: str | None = None,
        env: Mapping[str, str] | None = None,
    ) -> CommandResult:
        # cwd/env apply on the remote side via the command itself, not the local ssh call.
        return run_local(self.build_argv(command), timeout=timeout, retries=retries)


def make_provider(spec: str) -> Provider:
    """Resolve a policy provider string ("local" or "ssh:host[:user]") to a Provider."""
    if spec == "local":
        return LocalProvider()
    if spec.startswith("ssh:"):
        rest = spec[len("ssh:") :]
        host, _, user = rest.partition(":")
        return SSHProvider(host, user=user or None)
    raise ValueError(f"unknown provider spec: {spec!r}")
