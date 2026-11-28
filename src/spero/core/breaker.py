# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# __creation__ = 2026-11-28
# __author__ = "jndjama (Joy Ndjama)"
# __copyright__ = "Copyright 2026 ALTIKVA."
# __licence__ = "Apache-2.0 (https://www.apache.org/licenses/LICENSE-2.0)"
# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# Description: Crash-loop breaker: stop remediating a target that keeps dying.

"""Crash-loop breaker: stop remediating a target that keeps dying.

A target with a ``breaker`` keeps the times of its successful remediations. When
``max_restarts`` of them fall inside the last ``window_s`` seconds and the target
fails again, the breaker trips: no more remediation until a human resets it.
The state goes through a :class:`BreakerStore`, so a tripped breaker survives a
restart of the daemon when the store is persistent.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from spero.core.models import BreakerSpec


@dataclass(slots=True)
class BreakerState:
    restarts: list[float] = field(default_factory=list)  # epoch seconds
    tripped_at: float | None = None
    detail: str = ""

    @property
    def tripped(self) -> bool:
        return self.tripped_at is not None

    def prune(self, spec: BreakerSpec, now: float) -> None:
        """Forget the restarts that fell out of the window."""
        self.restarts = [t for t in self.restarts if now - t < spec.window_s]

    def should_trip(self, spec: BreakerSpec, now: float) -> bool:
        self.prune(spec, now)
        return len(self.restarts) >= spec.max_restarts


class BreakerStore(Protocol):
    """Where breaker state lives. Implementations are blocking; the engine calls
    them from a worker thread."""

    def load(self, target: str) -> BreakerState: ...

    def save(self, target: str, state: BreakerState) -> None: ...

    def reset(self, target: str) -> bool:
        """Clear the state of ``target``. Returns True if it was tripped."""
        ...


class MemoryBreakerStore:
    """Process-local store: the default, and what tests use."""

    def __init__(self) -> None:
        self._states: dict[str, BreakerState] = {}

    def load(self, target: str) -> BreakerState:
        s = self._states.get(target)
        return BreakerState(list(s.restarts), s.tripped_at, s.detail) if s else BreakerState()

    def save(self, target: str, state: BreakerState) -> None:
        self._states[target] = BreakerState(list(state.restarts), state.tripped_at, state.detail)

    def reset(self, target: str) -> bool:
        s = self._states.pop(target, None)
        return s is not None and s.tripped
