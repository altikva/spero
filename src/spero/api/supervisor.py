# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# __creation__ = 2026-06-06
# __author__ = "jndjama (Joy Ndjama)"
# __copyright__ = "Copyright 2026 ALTIKVA."
# __licence__ = "MIT & CC BY-NC-SA (https://www.altikva.com/licenses/LICENSE-1.0)"
# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# Description: Supervisor: drives the engine in the background and exposes live
#              status + recent events as JSON for the control-plane API.

"""A long-lived supervisor that backs the control-plane API.

`spero serve` runs one of these: it drives the supervision loop (the same
`core.watch` scheduler as `spero watch`) in the background and keeps the latest
per-target outcome in memory, so the API can answer "what is this worker
supervising right now, and how is it doing" without re-probing. This is the read
model a remote owner observes (see `spero top --remote`).
"""

from __future__ import annotations

import asyncio

from spero.core.engine import Approver as ApproverType
from spero.core.engine import Engine, TargetOutcome, deny_all
from spero.core.models import Policy, TargetPolicy
from spero.core.watch import watch


class Supervisor:
    """Runs the watch loop and serves its live state as plain dicts."""

    def __init__(
        self,
        policy: Policy,
        *,
        store_engine: object | None = None,
        approver: ApproverType = deny_all,
    ) -> None:
        self.policy = policy
        self.engine = Engine(policy, approver=approver)
        self.store_engine = store_engine
        self.latest: dict[str, TargetOutcome] = {}
        self._stop = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    def _on_outcome(self, outcome: TargetOutcome) -> None:
        self.latest[outcome.target] = outcome

    async def start(self) -> None:
        self._stop.clear()
        self._task = asyncio.create_task(
            watch(
                self.engine,
                self.policy,
                store_engine=self.store_engine,
                on_outcome=self._on_outcome,
                stop=self._stop,
            )
        )

    async def stop(self) -> None:
        self._stop.set()
        if self._task is not None:
            await self._task
            self._task = None

    def status(self) -> dict[str, object]:
        """Live status: the freeze flag and one entry per declared target."""
        return {
            "frozen": self.policy.frozen,
            "targets": [
                self._target_status(t.name, t.provider, t.probe.type) for t in self.policy.targets
            ],
        }

    def _target_status(self, name: str, provider: str, probe: str) -> dict[str, object]:
        o = self.latest.get(name)
        if o is None:  # not probed yet
            return {
                "target": name,
                "provider": provider,
                "probe": probe,
                "healthy": None,
                "failures": 0,
                "detail": "",
                "action": None,
            }
        return {
            "target": name,
            "provider": provider,
            "probe": probe,
            "healthy": o.healthy,
            "failures": o.failures,
            "detail": o.detail,
            "action": _action_dict(o),
        }

    async def object_yaml(self, name: str) -> str:
        """YAML of the object the named target supervises. Raises KeyError if unknown."""
        from spero.core.inspect import object_yaml

        return await object_yaml(self._target(name))

    async def object_logs(self, name: str, *, tail: int = 200) -> str:
        """Recent log lines of the named target's pod(s). Raises KeyError if unknown."""
        from spero.core.inspect import object_logs

        return await object_logs(self._target(name), tail=tail)

    def _target(self, name: str) -> TargetPolicy:
        target = next((t for t in self.policy.targets if t.name == name), None)
        if target is None:
            raise KeyError(name)
        return target

    def events(self, limit: int = 50) -> list[dict[str, str]]:
        """Recent events, newest last. From the store if persisting, else in-memory."""
        from sqlalchemy import Engine as SAEngine

        if isinstance(self.store_engine, SAEngine):
            from spero.store import recent_events

            rows = list(reversed(recent_events(self.store_engine, limit=limit)))
        else:
            rows = self.engine.events[-limit:]
        return [
            {"node": e.node, "target": e.target, "kind": e.kind, "detail": e.detail} for e in rows
        ]


def _action_dict(o: TargetOutcome) -> dict[str, str] | None:
    if o.action is None:
        return None
    return {
        "remediation": o.action.remediation,
        "status": o.action.status.value,
        "detail": o.action.detail,
    }
