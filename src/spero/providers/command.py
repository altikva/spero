"""Local command execution.

This is the modernized port of ``utilities.commons.remote.connexion.run_command``
from the original bot. Three things changed on the way over:

* the bare ``(rc, out, err)`` tuple became a typed ``CommandResult``;
* the SIGALRM-based timeout (Unix-only, not thread-safe) became
  ``subprocess.run(timeout=...)``, which works under threads and on any platform;
* every failure mode now returns a ``CommandResult`` instead of raising, so the
  supervision loop never crashes on a missing binary or bad quoting -- the common
  case for a remediation that can't run is a non-zero result, not an exception.

Retry semantics: a command is attempted ``retries + 1`` times and stops as soon
as it succeeds. A timeout is, by default, *not* retried -- blindly re-running a
slow command amplifies load on an already-struggling host. Set
``retry_on_timeout=True`` to opt in.
"""

from __future__ import annotations

import os
import shlex
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

# Conventional return codes (match the shell): 124 = timed out, 127 = not found.
TIMEOUT_RC = 124
NOT_FOUND_RC = 127


@dataclass(slots=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str
    command: str = ""

    @property
    def ok(self) -> bool:
        return self.returncode == 0

    @property
    def timed_out(self) -> bool:
        return self.returncode == TIMEOUT_RC


def _as_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode(errors="replace")
    return value


def run_local(
    command: str | Sequence[str],
    *,
    timeout: float | None = None,
    retries: int = 0,
    retry_on_timeout: bool = False,
    cwd: str | None = None,
    env: Mapping[str, str] | None = None,
    env_replace: bool = False,
    shell: bool = False,
) -> CommandResult:
    """Run a command on the local host and return a :class:`CommandResult`.

    By default the command runs without a shell: a string is tokenized with
    ``shlex.split`` and the argument vector is passed straight to the OS, which
    avoids the shell-injection footgun the original carried via ``shell=True``.
    Pass ``shell=True`` explicitly when you really need a pipeline.

    ``env`` is *merged* onto the current environment by default (so ``PATH`` and
    friends survive); pass ``env_replace=True`` to use it as the whole environment.
    This function does not raise for command failures -- a missing executable,
    malformed quoting, or a timeout all come back as a non-zero ``CommandResult``.
    """
    display = command if isinstance(command, str) else shlex.join(command)

    # Tokenize up front, inside the contract: bad quoting is a result, not a crash.
    if isinstance(command, str) and not shell:
        try:
            args: str | Sequence[str] = shlex.split(command)
        except ValueError as exc:
            return CommandResult(NOT_FOUND_RC, "", f"invalid command: {exc}", display)
    else:
        args = command

    if env is None:
        proc_env: Mapping[str, str] | None = None
    elif env_replace:
        proc_env = dict(env)
    else:
        proc_env = {**os.environ, **env}

    result = CommandResult(returncode=-1, stdout="", stderr="", command=display)
    for _attempt in range(retries + 1):
        try:
            proc = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=cwd,
                env=proc_env,
                shell=shell,
            )
            result = CommandResult(proc.returncode, proc.stdout, proc.stderr, display)
        except subprocess.TimeoutExpired as exc:
            stderr = _as_text(exc.stderr)
            note = f"timed out after {timeout}s"
            result = CommandResult(
                TIMEOUT_RC,
                _as_text(exc.stdout),
                f"{stderr}\n{note}".strip(),
                display,
            )
            if not retry_on_timeout:
                break
        except OSError as exc:
            # missing binary, permission denied, etc. -- the remediation can't run.
            result = CommandResult(NOT_FOUND_RC, "", f"{type(exc).__name__}: {exc}", display)
        if result.ok:
            break
    return result
