# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# __creation__ = 2026-06-03
# __author__ = "jndjama (Joy Ndjama)"
# __copyright__ = "Copyright 2026 ALTIKVA."
# __licence__ = "MIT & CC BY-NC-SA (http://www.altikva.com/licenses/LICENSE-1.0)"
# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#

"""Test doubles: a Provider whose command results are scripted by a handler."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence

from spero.providers.base import Provider
from spero.providers.command import CommandResult

Handler = Callable[[str | Sequence[str]], CommandResult]


class ScriptedProvider(Provider):
    name = "fake"

    def __init__(self, handler: Handler) -> None:
        self._handler = handler
        self.commands: list[str | Sequence[str]] = []

    async def run(
        self,
        command: str | Sequence[str],
        *,
        timeout: float | None = None,
        retries: int = 0,
        cwd: str | None = None,
        env: Mapping[str, str] | None = None,
    ) -> CommandResult:
        self.commands.append(command)
        return self._handler(command)


def fixed(returncode: int = 0, stdout: str = "", stderr: str = "") -> Handler:
    def handler(command: str | Sequence[str]) -> CommandResult:
        return CommandResult(returncode, stdout, stderr, str(command))

    return handler


def systemd_handler(active: bool, *, restart_ok: bool = True) -> Handler:
    """Drives SystemdProbe (is-active) and RestartService (restart) for engine tests."""

    def handler(command: str | Sequence[str]) -> CommandResult:
        argv = [command] if isinstance(command, str) else list(command)
        if "is-active" in argv:
            return CommandResult(0 if active else 3, "active" if active else "inactive", "")
        if "restart" in argv:
            return CommandResult(0 if restart_ok else 1, "", "" if restart_ok else "boom")
        return CommandResult(0, "", "")

    return handler
