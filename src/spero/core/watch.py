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
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

from apscheduler.events import EVENT_JOB_ERROR, JobExecutionEvent
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from spero.core.engine import Engine, TargetOutcome
from spero.core.models import Policy, TargetPolicy

logger = logging.getLogger(__name__)

OnOutcome = Callable[[TargetOutcome], Awaitable[None] | None] | None


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

    now = datetime.now(UTC)
    for i, target in enumerate(policy.targets):
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
    return scheduler


async def watch(
    engine: Engine,
    policy: Policy,
    *,
    store_engine: object | None = None,
    on_outcome: OnOutcome = None,
    stop: asyncio.Event | None = None,
) -> None:
    """Run the scheduler until ``stop`` is set, then shut it down cleanly."""
    stop = stop or asyncio.Event()
    scheduler = build_scheduler(engine, policy, store_engine=store_engine, on_outcome=on_outcome)
    scheduler.start()
    try:
        await stop.wait()
    finally:
        if scheduler.running:
            scheduler.shutdown(wait=False)
