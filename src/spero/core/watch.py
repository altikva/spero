# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# __creation__ = 2026-06-03
# __author__ = "jndjama (Joy Ndjama)"
# __copyright__ = "Copyright 2026 ALTIKVA."
# __licence__ = "MIT & CC BY-NC-SA (https://www.altikva.com/licenses/LICENSE-1.0)"
# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# Description: Continuous supervision: run the engine on a schedule until told to stop.

"""Continuous supervision: run the engine on a schedule until told to stop.

Each target gets its own APScheduler interval job at its probe's ``interval``, with
``max_instances=1`` + ``coalesce`` so a slow probe can't pile up or overlap itself.
The loop is just an asyncio event the caller sets to stop (SIGINT/SIGTERM in the CLI).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Sequence
from datetime import UTC, datetime, timedelta

from apscheduler.events import EVENT_JOB_ERROR, JobExecutionEvent
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from spero.core.engine import Engine, PolicyChange, TargetOutcome
from spero.core.models import Policy, TargetPolicy
from spero.core.policy import PolicyReloader, PolicyReloadError

logger = logging.getLogger(__name__)

OnOutcome = Callable[[TargetOutcome], Awaitable[None] | None] | None
OnReload = Callable[[PolicyChange | PolicyReloadError], None] | None


async def _tick(
    engine: Engine,
    target: TargetPolicy,
    store_engine: object | None,
    on_outcome: OnOutcome,
) -> None:
    outcome = await engine.supervise(target)
    if store_engine is not None:
        await engine.persist(store_engine)
    if on_outcome is not None:
        result = on_outcome(outcome)
        if asyncio.iscoroutine(result):
            await result


def build_scheduler(
    engine: Engine,
    policy: Policy,
    *,
    store_engine: object | None = None,
    on_outcome: OnOutcome = None,
    default_interval: int = 30,
) -> AsyncIOScheduler:
    """One interval job per target, started staggered then every probe interval."""
    scheduler = AsyncIOScheduler(timezone=UTC)

    def _on_error(event: JobExecutionEvent) -> None:
        logger.error("watch job %s failed: %s", event.job_id, event.exception)

    scheduler.add_listener(_on_error, EVENT_JOB_ERROR)

    _add_jobs(scheduler, engine, policy.targets, store_engine, on_outcome, default_interval)
    return scheduler


def _add_jobs(
    scheduler: AsyncIOScheduler,
    engine: Engine,
    targets: Sequence[TargetPolicy],
    store_engine: object | None,
    on_outcome: OnOutcome,
    default_interval: int,
) -> None:
    now = datetime.now(UTC)
    for i, target in enumerate(targets):
        interval = target.probe.interval or default_interval
        # Stagger first runs so N targets don't all fire (and all persist) at once.
        first = now + timedelta(seconds=min(i * 0.5, float(interval)))
        scheduler.add_job(
            _tick,
            "interval",
            seconds=interval,
            args=[engine, target, store_engine, on_outcome],
            id=target.name,
            max_instances=1,
            coalesce=True,
            misfire_grace_time=interval,
            next_run_time=first,
        )


def reconcile_scheduler(
    scheduler: AsyncIOScheduler,
    engine: Engine,
    policy: Policy,
    change: PolicyChange,
    *,
    store_engine: object | None = None,
    on_outcome: OnOutcome = None,
    default_interval: int = 30,
) -> None:
    """Bring the jobs in line with a reloaded policy.

    Only added, removed and changed targets are touched. The job of an unchanged
    target is left alone, so a reload does not shift its schedule.
    """
    for name in (*change.removed, *change.changed):
        if scheduler.get_job(name) is not None:
            scheduler.remove_job(name)
    by_name = {t.name: t for t in policy.targets}
    fresh = [by_name[name] for name in (*change.added, *change.changed)]
    _add_jobs(scheduler, engine, fresh, store_engine, on_outcome, default_interval)


async def watch(
    engine: Engine,
    policy: Policy,
    *,
    store_engine: object | None = None,
    on_outcome: OnOutcome = None,
    stop: asyncio.Event | None = None,
    reloader: PolicyReloader | None = None,
    reload_now: asyncio.Event | None = None,
    on_reload: OnReload = None,
    poll_interval: float = 2.0,
) -> None:
    """Run the scheduler until ``stop`` is set, then shut it down cleanly.

    With a ``reloader`` the policy can change while running: setting ``reload_now``
    (SIGHUP in the CLI) reloads at once, and a reloader built with ``on_change``
    also picks up edits to the file. A file that fails to load never stops
    supervision; the current policy stays in force and ``on_reload`` gets the error.
    """
    stop = stop or asyncio.Event()
    scheduler = build_scheduler(engine, policy, store_engine=store_engine, on_outcome=on_outcome)
    scheduler.start()
    try:
        if reloader is None:
            await stop.wait()
            return
        reload_now = reload_now or asyncio.Event()
        while not await _stop_or_wake(stop, reload_now, poll_interval):
            force = reload_now.is_set()
            reload_now.clear()
            try:
                new_policy = reloader.poll(force=force)
            except PolicyReloadError as exc:
                if on_reload is not None:
                    on_reload(exc)
                else:
                    logger.warning("policy reload skipped, keeping the current policy: %s", exc)
                continue
            if new_policy is None:
                continue
            change = await engine.apply_policy(new_policy)
            reconcile_scheduler(
                scheduler,
                engine,
                new_policy,
                change,
                store_engine=store_engine,
                on_outcome=on_outcome,
            )
            if on_reload is not None:
                on_reload(change)
            else:
                logger.info("policy reloaded: %s", change.summary())
    finally:
        if scheduler.running:
            scheduler.shutdown(wait=False)


async def _stop_or_wake(stop: asyncio.Event, wake: asyncio.Event, timeout: float) -> bool:
    """Wait for ``stop``, ``wake`` or the timeout. True means stop."""
    waiters = [asyncio.ensure_future(stop.wait()), asyncio.ensure_future(wake.wait())]
    try:
        await asyncio.wait(waiters, timeout=timeout, return_when=asyncio.FIRST_COMPLETED)
    finally:
        for waiter in waiters:
            waiter.cancel()
    return stop.is_set()
