"""The Provider interface every execution backend implements."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence

from spero.providers.command import CommandResult


class Provider(ABC):
    """Executes commands against a target (a host, a pod, ...)."""

    name: str

    @abstractmethod
    def run(
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
