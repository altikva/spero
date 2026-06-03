"""Local command execution.

This is the modernized port of ``utilities.commons.remote.connexion.run_command``
from the original bot. Two things changed on the way over:

* the bare ``(rc, out, err)`` tuple became a typed ``CommandResult``;
* the SIGALRM-based timeout (Unix-only, not thread-safe) became
  ``subprocess.run(timeout=...)``, which works under threads and on any platform.

Retry-on-failure behaviour is preserved: a command is attempted ``retries + 1``
times and stops as soon as it succeeds.
"""

from __future__ import annotations

import shlex
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

# Conventional return code for a timed-out command (matches GNU `timeout`).
TIMEOUT_RC = 124


@dataclass(slots=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str
    command: str = ""

    @property
    def ok(self) -> bool:
        return self.returncode == 0


def run_local(
    command: str | Sequence[str],
    *,
    timeout: float | None = None,
    retries: int = 0,
    cwd: str | None = None,
    env: Mapping[str, str] | None = None,
    shell: bool = False,
) -> CommandResult:
    """Run a command on the local host and return a :class:`CommandResult`.

    By default the command is run without a shell: a string is tokenized with
    ``shlex.split`` and the argument vector is passed straight to the OS, which
    avoids the shell-injection footgun the original carried via ``shell=True``.
    Pass ``shell=True`` explicitly when you really need a pipeline.
    """
    if isinstance(command, str):
        display = command
        args: str | Sequence[str] = command if shell else shlex.split(command)
    else:
        display = shlex.join(command)
        args = command

    result = CommandResult(returncode=-1, stdout="", stderr="", command=display)
    for _attempt in range(retries + 1):
        try:
            proc = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=cwd,
                env=dict(env) if env is not None else None,
                shell=shell,
            )
            result = CommandResult(proc.returncode, proc.stdout, proc.stderr, display)
        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout or ""
            if isinstance(stdout, bytes):
                stdout = stdout.decode(errors="replace")
            result = CommandResult(TIMEOUT_RC, stdout, f"timed out after {timeout}s", display)
        if result.ok:
            break
    return result
