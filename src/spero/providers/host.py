"""Host providers: run commands locally or over SSH (async).

``LocalProvider`` runs on the machine Spero lives on via asyncio subprocesses.
``SSHProvider`` uses asyncssh, the native-async transport that fits a control
plane fanning remediation across many hosts concurrently.

Provider policy strings: ``local`` or ``ssh:[user@]host[:port]``.
"""

from __future__ import annotations

import asyncio
import shlex
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import asyncssh

from spero.providers.base import Provider
from spero.providers.command import NOT_FOUND_RC, TIMEOUT_RC, CommandResult, run_local_async

# Sentinel: use asyncssh's default known_hosts handling (verify against the user's
# ~/.ssh/known_hosts). Pass known_hosts=None to a provider to DISABLE verification
# (trust-on-first-use, dev only); pass a path to use a managed known_hosts file.
_DEFAULT_KNOWN_HOSTS = object()


class LocalProvider(Provider):
    name = "local"

    async def run(
        self,
        command: str | Sequence[str],
        *,
        timeout: float | None = None,
        retries: int = 0,
        cwd: str | None = None,
        env: Mapping[str, str] | None = None,
    ) -> CommandResult:
        return await run_local_async(command, timeout=timeout, retries=retries, cwd=cwd, env=env)


class SSHProvider(Provider):
    name = "ssh"

    def __init__(
        self,
        host: str,
        *,
        user: str | None = None,
        port: int | None = None,
        known_hosts: Any = _DEFAULT_KNOWN_HOSTS,
        connect_timeout: float = 10.0,
    ) -> None:
        self.host = host
        self.user = user
        self.port = port
        self.known_hosts = known_hosts
        self.connect_timeout = connect_timeout

    @property
    def destination(self) -> str:
        return f"{self.user}@{self.host}" if self.user else self.host

    def _connect_kwargs(self) -> dict[str, Any]:
        kwargs: dict[str, Any] = {"connect_timeout": self.connect_timeout}
        if self.port is not None:
            kwargs["port"] = self.port
        if self.user is not None:
            kwargs["username"] = self.user
        if self.known_hosts is not _DEFAULT_KNOWN_HOSTS:
            kwargs["known_hosts"] = self.known_hosts
        return kwargs

    async def run(
        self,
        command: str | Sequence[str],
        *,
        timeout: float | None = None,
        retries: int = 0,
        cwd: str | None = None,
        env: Mapping[str, str] | None = None,
    ) -> CommandResult:
        if cwd is not None or env is not None:
            # Bake cwd/env into the command until we wire them through asyncssh.
            raise NotImplementedError("SSHProvider does not yet support cwd/env; use the command")
        remote = command if isinstance(command, str) else shlex.join(command)

        result = CommandResult(returncode=-1, stdout="", stderr="", command=remote)
        for _attempt in range(retries + 1):
            try:
                # Bound the WHOLE call (connect + run) by `timeout`; connect_timeout
                # is only the floor for the TCP/handshake/auth phase. asyncssh.Error
                # and TimeoutError both surface here; the async-with closes the
                # connection on timeout via __aexit__ (verified leak-free).
                completed = await asyncio.wait_for(self._exec(remote), timeout)
                result = CommandResult(
                    completed.exit_status or 0,
                    _ssh_text(completed.stdout),
                    _ssh_text(completed.stderr),
                    remote,
                )
            except TimeoutError:
                result = CommandResult(TIMEOUT_RC, "", f"timed out after {timeout}s", remote)
                break
            except (OSError, asyncssh.Error) as exc:
                result = CommandResult(NOT_FOUND_RC, "", f"{type(exc).__name__}: {exc}", remote)
            if result.ok:
                break
        return result

    async def _exec(self, remote: str) -> asyncssh.SSHCompletedProcess:
        async with asyncssh.connect(self.host, **self._connect_kwargs()) as conn:
            return await conn.run(remote, check=False)


def _ssh_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode(errors="replace")
    return str(value)


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


def make_provider(spec: str, *, known_hosts: Any = _DEFAULT_KNOWN_HOSTS) -> Provider:
    """Resolve a policy provider string to a concrete Provider."""
    kind, target = parse_provider_spec(spec)
    if kind == "local":
        return LocalProvider()
    assert target is not None
    return SSHProvider(target.host, user=target.user, port=target.port, known_hosts=known_hosts)
