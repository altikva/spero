# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# __creation__ = 2026-06-03
# __author__ = "jndjama (Joy Ndjama)"
# __copyright__ = "Copyright 2026 ALTIKVA."
# __licence__ = "MIT & CC BY-NC-SA (https://www.altikva.com/licenses/LICENSE-1.0)"
# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# Description: Alerter interface: fire on first failure, resolve on recovery.

"""Alerter interface: fire on first failure, resolve on recovery.

This is the open/resolve idea ported from the bot's save_one_alert /
acknowledge_one_alert, minus the per-row DB bookkeeping (the engine owns state).
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class Alerter(ABC):
    @abstractmethod
    async def fire(self, target: str, detail: str) -> None:
        """A target just transitioned to unhealthy."""

    @abstractmethod
    async def resolve(self, target: str, detail: str) -> None:
        """A previously-unhealthy target recovered."""


class NullAlerter(Alerter):
    """Does nothing. The default when no channel is configured."""

    async def fire(self, target: str, detail: str) -> None:
        return None

    async def resolve(self, target: str, detail: str) -> None:
        return None
