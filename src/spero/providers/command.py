# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# __creation__ = 2026-06-03
# __author__ = "jndjama (Joy Ndjama)"
# __copyright__ = "Copyright 2026 ALTIKVA."
# __licence__ = "MIT & CC BY-NC-SA (http://www.altikva.com/licenses/LICENSE-1.0)"
# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# Description: Local command execution, sync and async.

"""Local command execution, sync and async.

The modernized port of ``utilities.commons.remote.connexion.run_command`` from the
original bot. Changes on the way over:

* the bare ``(rc, out, err)`` tuple became a typed ``CommandResult``;
* the SIGALRM timeout (Unix-only, not thread-safe) became real timeouts;
* every failure mode returns a ``CommandResult`` instead of raising, so the
  supervision loop never crashes on a missing binary or bad quoting;
* an ``async`` variant (:func:`run_local_async`) backs the async provider layer.

Retry semantics: a command is attempted ``retries + 1`` times and stops on the
first success. A timeout is not retried by default (re-running a slow command
amplifies load on a struggling host); opt in with ``retry_on_timeout=True``.
"""

from __future__ import annotations

import asyncio
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


def _prepare_args(
    command: str | Sequence[str], shell: bool
) -> tuple[str | Sequence[str] | None, str, str]:
    """Return (args, display, error). On bad quoting, args is None and error is set."""
    display = command if isinstance(command, str) else shlex.join(command)
    if isinstance(command, str) and not shell:
        try:
            return shlex.split(command), display, ""
        except ValueError as exc:
            return None, display, f"invalid command: {exc}"
    return command, display, ""


def _prepare_env(env: Mapping[str, str] | None, env_replace: bool) -> dict[str, str] | None:
    if env is None:
        return None
    if env_replace:
        return dict(env)
    return {**os.environ, **env}


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
    """Run a command on the local host (blocking) and return a :class:`CommandResult`.

    Runs without a shell by default (a string is tokenized with ``shlex.split``),
    avoiding the injection footgun the original carried via ``shell=True``. ``env``
    is merged onto the current environment unless ``env_replace=True``. Never raises
    for command failures: missing binary, bad quoting, and timeout all come back as
    a non-zero result.
    """
    args, display, err = _prepare_args(command, shell)
    if args is None:
        return CommandResult(NOT_FOUND_RC, "", err, display)
    proc_env = _prepare_env(env, env_replace)

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
            note = f"timed out after {timeout}s"
            result = CommandResult(
                TIMEOUT_RC, _as_text(exc.stdout), f"{_as_text(exc.stderr)}\n{note}".strip(), display
            )
            if not retry_on_timeout:
                break
        except OSError as exc:
            result = CommandResult(NOT_FOUND_RC, "", f"{type(exc).__name__}: {exc}", display)
        if result.ok:
            break
    return result


async def run_local_async(
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
    """Async twin of :func:`run_local`, built on ``asyncio`` subprocesses."""
    args, display, err = _prepare_args(command, shell)
    if args is None:
        return CommandResult(NOT_FOUND_RC, "", err, display)
    proc_env = _prepare_env(env, env_replace)

    result = CommandResult(returncode=-1, stdout="", stderr="", command=display)
    for _attempt in range(retries + 1):
        try:
            if shell:
                assert isinstance(args, str)
                proc = await asyncio.create_subprocess_shell(
                    args,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=cwd,
                    env=proc_env,
                )
            else:
                argv = [args] if isinstance(args, str) else list(args)
                proc = await asyncio.create_subprocess_exec(
                    *argv,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=cwd,
                    env=proc_env,
                )
        except OSError as exc:
            # spawn failed (missing binary, EACCES); never ok, so just try again.
            result = CommandResult(NOT_FOUND_RC, "", f"{type(exc).__name__}: {exc}", display)
            continue

        try:
            out, errb = await asyncio.wait_for(proc.communicate(), timeout)
            result = CommandResult(proc.returncode or 0, _as_text(out), _as_text(errb), display)
        except TimeoutError:
            # kill + wait reaps the child and closes the pipe transports cleanly
            # (verified leak-free on CPython 3.12, even with a full stdout buffer).
            proc.kill()
            await proc.wait()
            result = CommandResult(TIMEOUT_RC, "", f"timed out after {timeout}s", display)
            if not retry_on_timeout:
                break
        if result.ok:
            break
    return result
