"""Continuous supervision: run the engine on a schedule until told to stop.

Each target gets its own APScheduler interval job at its probe's ``interval``, with
``max_instances=1`` + ``coalesce`` so a slow probe can't pile up or overlap itself.
The loop is just an asyncio event the caller sets to stop (SIGINT/SIGTERM in the CLI).
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from spero.core.engine import Engine, TargetOutcome
from spero.core.models import Policy, TargetPolicy

OnOutcome = Callable[[TargetOutcome], Awaitable[None] | None] | None


async def _tick(
    engine: Engine,
    target: TargetPolicy,
    store_engine: object | None,
    on_outcome: OnOutcome,
) -> None:
    outcome = await engine.supervise(target)
    if store_engine is not None:
        engine.persist(store_engine)
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
    """One interval job per target, fired immediately then every probe interval."""
    scheduler = AsyncIOScheduler()
    for target in policy.targets:
        interval = target.probe.interval or default_interval
        scheduler.add_job(
            _tick,
            "interval",
            seconds=interval,
            args=[engine, target, store_engine, on_outcome],
            id=target.name,
            max_instances=1,
            coalesce=True,
            next_run_time=datetime.now(),
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
        scheduler.shutdown(wait=False)
