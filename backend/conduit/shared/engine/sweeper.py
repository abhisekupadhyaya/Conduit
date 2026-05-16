"""Reconciliation sweeper — the watchdog over the watchdog.

A slower secondary loop that hunts timers that *should* have fired but did
not, and orphaned states, then emits the "age of oldest unfired timer" metric
+ an alarm. This is what justifies running the engine on one cheap instance:
the safety net for "nothing is silently lost" (archi infrastructure §Timers).
"""
from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

log = logging.getLogger("conduit.engine")


async def sweep(s: AsyncSession) -> int:
    """Detect overdue/unfired timers; emit metric + alarm — never mutate.

    The slower reconciliation watchdog (AD5): a pure read. Uses DB `now()`
    as the only time source (AD5, never the host clock). Emits the
    "age of oldest unfired timer" metric via the engine logger (same path
    runner.py uses). Returns the overdue count; mutates no state — firing
    and dead-lettering remain runner.tick's job.
    """
    count, oldest = (await s.execute(text(
        "SELECT count(*), min(fire_at) FROM timer "
        "WHERE state='pending' AND fire_at < now()"))).one()
    if count:
        age = (await s.execute(text(
            "SELECT now() - :oldest"), {"oldest": oldest})).scalar_one()
        log.warning("age of oldest unfired timer: %s (overdue=%d)", age, count)
    return int(count)
