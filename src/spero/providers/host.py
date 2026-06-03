"""Host providers: run commands locally or over SSH.

``LocalProvider`` runs on the machine Spero lives on. ``SSHProvider`` shells out
to ``ssh`` for now (faithful to the original bot); a native async transport
(asyncssh) is the Phase 1 follow-up for the async control plane. Both share the
local executor in :mod:`spero.providers.command`.

Provider policy strings: ``local`` or ``ssh:[user@]host[:port]``.
"""

from __future__ import annotations

import shlex
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from spero.providers.base import Provider
from spero.providers.command import CommandResult, run_local

# Non-interactive, fail-fast SSH defaults. Replaces the bot's free-form SSH_OPTS.
# `accept-new` is trust-on-first-use: fine for dev, tighten to `yes` with a managed
# known_hosts in production (host-key policy is configurable per provider).
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
        port: int | None = None,
        ssh_opts: Sequence[str] = DEFAULT_SSH_OPTS,
        ssh_bin: str = "ssh",
    ) -> None:
        self.host = host
        self.user = user
        self.port = port
        self.ssh_opts = tuple(ssh_opts)
        self.ssh_bin = ssh_bin

    @property
    def destination(self) -> str:
        return f"{self.user}@{self.host}" if self.user else self.host

    def build_argv(self, command: str | Sequence[str]) -> list[str]:
        """Build the local ``ssh`` argument vector for a remote command."""
        remote = command if isinstance(command, str) else shlex.join(command)
        argv = [self.ssh_bin, *self.ssh_opts]
        if self.port is not None:
            argv += ["-p", str(self.port)]
        argv += [self.destination, remote]
        return argv

    def run(
        self,
        command: str | Sequence[str],
        *,
        timeout: float | None = None,
        retries: int = 0,
        cwd: str | None = None,
        env: Mapping[str, str] | None = None,
    ) -> CommandResult:
        if cwd is not None or env is not None:
            # Inject these remotely once we have a real transport; until then,
            # fail loud rather than silently ignore the caller's intent.
            raise NotImplementedError("SSHProvider does not yet support cwd/env; use the command")
        return run_local(self.build_argv(command), timeout=timeout, retries=retries)


@dataclass(frozen=True, slots=True)
class SSHTarget:
    host: str
    user: str | None = None
    port: int | None = None


def parse_ssh_dest(dest: str) -> SSHTarget:
    """Parse ``[user@]host[:port]`` into its parts. Raises ValueError on garbage.

    IPv6 literals must be bracketed (``[::1]:22``) to disambiguate the port colon.
    """
    user: str | None = None
    if "@" in dest:
        user, _, dest = dest.partition("@")
        if not user:
            raise ValueError("empty ssh user")

    port: int | None = None
    if dest.startswith("["):  # bracketed IPv6, optional :port after the bracket
        host, sep, tail = dest[1:].partition("]")
        if not sep:
            raise ValueError("unterminated IPv6 literal")
        if tail:
            if not tail.startswith(":"):
                raise ValueError(f"unexpected text after IPv6 host: {tail!r}")
            port = _parse_port(tail[1:])
    elif dest.count(":") == 1:  # host:port (a bare IPv6 would have many colons)
        host, _, raw_port = dest.partition(":")
        port = _parse_port(raw_port)
    else:
        host = dest

    if not host:
        raise ValueError("empty ssh host")
    return SSHTarget(host=host, user=user, port=port)


def _parse_port(raw: str) -> int:
    if not raw.isdigit():
        raise ValueError(f"invalid ssh port: {raw!r}")
    port = int(raw)
    if not 1 <= port <= 65535:
        raise ValueError(f"ssh port out of range: {port}")
    return port


def parse_provider_spec(spec: str) -> tuple[str, SSHTarget | None]:
    """Validate a policy provider string. Returns (kind, ssh_target | None).

    Pure and side-effect free so it can back a Pydantic validator -- bad provider
    strings then fail at policy load, not mid-remediation.
    """
    if spec == "local":
        return "local", None
    if spec.startswith("ssh:"):
        return "ssh", parse_ssh_dest(spec[len("ssh:") :])
    raise ValueError(
        f"unknown provider spec: {spec!r} (expected 'local' or 'ssh:[user@]host[:port]')"
    )


def make_provider(spec: str, *, ssh_opts: Sequence[str] = DEFAULT_SSH_OPTS) -> Provider:
    """Resolve a policy provider string to a concrete Provider."""
    kind, target = parse_provider_spec(spec)
    if kind == "local":
        return LocalProvider()
    assert target is not None
    return SSHProvider(target.host, user=target.user, port=target.port, ssh_opts=ssh_opts)
