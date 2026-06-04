# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# __creation__ = 2026-06-03
# __author__ = "jndjama (Joy Ndjama)"
# __copyright__ = "Copyright 2026 ALTIKVA."
# __licence__ = "MIT & CC BY-NC-SA (http://www.altikva.com/licenses/LICENSE-1.0)"
# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#

"""The Provider interface every execution backend implements."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from typing import ClassVar

from spero.providers.command import CommandResult


class Provider(ABC):
    """Executes commands against a target (a host, a pod, ...). Async."""

    name: ClassVar[str] = ""

    @abstractmethod
    async def run(
        self,
        command: str | Sequence[str],
        *,
        timeout: float | None = None,
        retries: int = 0,
        cwd: str | None = None,
        env: Mapping[str, str] | None = None,
    ) -> CommandResult:
        """Run ``command`` and return its result."""
        raise NotImplementedError
