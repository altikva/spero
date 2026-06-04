# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# __creation__ = 2026-06-03
# __author__ = "jndjama (Joy Ndjama)"
# __copyright__ = "Copyright 2026 ALTIKVA."
# __licence__ = "MIT & CC BY-NC-SA (http://www.altikva.com/licenses/LICENSE-1.0)"
# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#

"""The supervision engine: probe -> count failures -> remediate -> alert.

A faithful, typed re-encoding of the bot's ``perform_oversee`` loop. Per target:
check health; on failure increment a counter and, once the failure count reaches a
remediation's ``max_attempts``, run the most-escalated eligible remediation -- but
only as far as its ``autonomy`` allows:

* ``suggest`` -> record a suggestion, never act;
* ``gated``   -> act only if the ``approver`` says yes (human-in-the-loop);
* ``auto``    -> act unattended.

``policy.frozen`` is the global action freeze; nothing is applied while it is set.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import StrEnum

from spero.alerting.base import Alerter, NullAlerter
from spero.core.models import Autonomy, Policy, RemediationSpec, TargetPolicy
from spero.probes import build_probe
from spero.providers.base import Provider
from spero.providers.host import make_provider
from spero.remediations import build_remediation
from spero.store.models import Event

# Decides whether a `gated` remediation may run. Return True to approve.
Approver = Callable[[TargetPolicy, RemediationSpec], Awaitable[bool]]
ProviderFactory = Callable[[str], Provider]


async def deny_all(target: TargetPolicy, spec: RemediationSpec) -> bool:
    """Default approver for unattended runs: gated actions wait for a human."""
    return False


class ActionStatus(StrEnum):
    waiting = "waiting"  # failure count below the remediation threshold
    frozen = "frozen"  # blocked by the global action freeze
    suggested = "suggested"  # autonomy=suggest, not executed
    awaiting_approval = "awaiting_approval"  # autonomy=gated, approver declined
    applied = "applied"  # executed successfully
    failed = "failed"  # executed but the action reported failure


@dataclass(slots=True)
class ActionOutcome:
    remediation: str
    status: ActionStatus
    detail: str = ""


@dataclass(slots=True)
class TargetOutcome:
    target: str
    healthy: bool
    detail: str
    failures: int = 0
    action: ActionOutcome | None = None


class Engine:
    def __init__(
        self,
        policy: Policy,
        *,
        provider_factory: ProviderFactory = make_provider,
        approver: Approver = deny_all,
        alerter: Alerter | None = None,
    ) -> None:
        self.policy = policy
        self.provider_factory = provider_factory
        self.approver = approver
        self.alerter = alerter or NullAlerter()
        self._failures: dict[str, int] = {}
        self._open_alerts: set[str] = set()
        self._events: list[Event] = []
        self._lock = asyncio.Lock()
        self._persist_lock = asyncio.Lock()

    @property
    def events(self) -> list[Event]:
        return list(self._events)

    def failures(self, target: str) -> int:
        return self._failures.get(target, 0)

    def _record(self, node: str, target: str, kind: str, detail: str) -> None:
        self._events.append(Event(node=node, target=target, kind=kind, detail=detail))

    async def run_cycle(self) -> list[TargetOutcome]:
        """Supervise every target once, concurrently.

        Serialized by a lock so overlapping callers (a scheduler plus a manual
        trigger) can't double-count failures or double-fire remediations.
        """
        async with self._lock:
            return list(await asyncio.gather(*(self._supervise(t) for t in self.policy.targets)))

    async def supervise(self, target: TargetPolicy) -> TargetOutcome:
        """Supervise a single target (fault-isolated).

        Used by the watch scheduler, which runs one job per target at the target's
        own interval with ``max_instances=1`` -- a target can't overlap itself, and
        distinct targets touch distinct state, so this needs no global lock. Don't
        mix concurrent ``supervise()`` and ``run_cycle()`` on the same engine.
        """
        return await self._supervise(target)

    async def _supervise(self, target: TargetPolicy) -> TargetOutcome:
        # One misbehaving target (a probe/remediation that *raises*) must never take
        # down supervision of the others, so isolate every target here.
        try:
            return await self._supervise_inner(target)
        except Exception as exc:
            self._record(target.provider, target.name, "error", f"{type(exc).__name__}: {exc}")
            failures = self._failures.get(target.name, 0)
            return TargetOutcome(target.name, False, f"error: {exc}", failures)

    async def _supervise_inner(self, target: TargetPolicy) -> TargetOutcome:
        provider = self.provider_factory(target.provider)
        probe = build_probe(target.probe)
        node = target.provider
        result = await probe.check(provider)

        if result.healthy:
            self._failures[target.name] = 0
            if target.name in self._open_alerts:
                self._open_alerts.discard(target.name)
                self._record(node, target.name, "info", f"recovered: {result.detail}")
                await self.alerter.resolve(target.name, result.detail)
            return TargetOutcome(target.name, True, result.detail, 0)

        n = self._failures.get(target.name, 0) + 1
        self._failures[target.name] = n
        self._record(node, target.name, "probe_fail", f"[{n}] {result.detail}")
        if target.name not in self._open_alerts:
            self._open_alerts.add(target.name)
            await self.alerter.fire(target.name, result.detail)

        action = await self._select_and_act(node, target, provider, n)
        return TargetOutcome(target.name, False, result.detail, n, action)

    async def _select_and_act(
        self, node: str, target: TargetPolicy, provider: Provider, n: int
    ) -> ActionOutcome | None:
        if not target.remediations:
            return None

        # The list is the escalation ladder (validated non-decreasing max_attempts):
        # the most-escalated eligible step is the LAST one whose threshold is reached.
        eligible = [s for s in target.remediations if n >= s.max_attempts]
        if not eligible:
            nxt = target.remediations[0]
            return ActionOutcome(
                nxt.type, ActionStatus.waiting, f"{n}/{nxt.max_attempts} failures before {nxt.type}"
            )
        spec = eligible[-1]

        if self.policy.frozen:
            self._record(node, target.name, "remediation", f"frozen: skipped {spec.type}")
            return ActionOutcome(spec.type, ActionStatus.frozen)

        if spec.autonomy is Autonomy.suggest:
            self._record(node, target.name, "remediation", f"suggested {spec.type}")
            return ActionOutcome(spec.type, ActionStatus.suggested, "autonomy=suggest")

        if spec.autonomy is Autonomy.gated and not await self.approver(target, spec):
            self._record(node, target.name, "remediation", f"awaiting approval: {spec.type}")
            return ActionOutcome(spec.type, ActionStatus.awaiting_approval)

        res = await build_remediation(spec).apply(provider)
        self._record(node, target.name, "remediation", f"{spec.type}: {res.detail}")
        if res.success:
            # Acted: clear the counter so we don't re-fire every cycle while the
            # target takes time to come back. A genuinely still-broken target will
            # re-accumulate failures and escalate again from the bottom of the ladder.
            self._failures[target.name] = 0
            return ActionOutcome(spec.type, ActionStatus.applied, res.detail)
        return ActionOutcome(spec.type, ActionStatus.failed, res.detail)

    async def persist(self, store_engine: object) -> None:
        """Flush collected events to the store, then clear them.

        Lock-guarded so concurrent ticks can't race the batch swap, and the
        (blocking) DB write runs in a worker thread so it never stalls the event
        loop -- the rest of the fleet keeps probing while one persist commits.
        """
        from sqlalchemy import Engine as SAEngine

        from spero.store.db import session_scope

        if not isinstance(store_engine, SAEngine):
            return
        async with self._persist_lock:
            if not self._events:
                return
            batch, self._events = self._events, []

            def _write() -> None:
                with session_scope(store_engine) as session:
                    session.add_all(batch)

            try:
                await asyncio.to_thread(_write)
            except Exception:
                self._events[:0] = batch  # in-place prepend preserves order
                raise
