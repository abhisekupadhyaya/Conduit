"""The lifecycle engine — in-process poll loop (AD4/AD5).

Runs inside the API process (single deployable). DB-backed timers: every tick
it claims due timers with `FOR UPDATE SKIP LOCKED` (so a second instance never
double-fires) and applies the transition + appends the event in one
transaction. Crash-safe: a restart simply resumes everything already due —
this is what keeps "nothing silently lost" true on cheap single-instance infra.
"""
from __future__ import annotations

import asyncio
import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from conduit.core.config import get_settings
from conduit.shared.db import SessionLocal
from conduit.shared.engine import spine
from conduit.shared.models import FailedTransition, Timer

log = logging.getLogger("conduit.engine")


async def run_engine(stop: asyncio.Event) -> None:
    s = get_settings()
    if not s.engine_enabled:
        log.info("engine disabled (CONDUIT_ENGINE_ENABLED=false)")
        return
    log.info("engine started; poll=%ss", s.engine_poll_seconds)
    while not stop.is_set():
        try:
            async with SessionLocal() as sess:
                await tick(sess)
                await sess.commit()
        except Exception:  # never let one bad tick kill the loop
            log.exception("engine tick failed")
        try:
            await asyncio.wait_for(stop.wait(), timeout=s.engine_poll_seconds)
        except TimeoutError:
            pass
    log.info("engine stopped")


async def tick(s: AsyncSession, *, limit: int = 50) -> int:
    """Claim & fire due pending timers.

    `FOR UPDATE SKIP LOCKED` so a second instance never double-fires; DB
    `now()` is the only time source (AD5). Returns the number of due-pending
    timers claimed this cycle — success counts via `_fire_one`, a caught
    failure is recorded by `_record_failed` and still counts (never silent).
    """
    rows = (await s.execute(text(
        "SELECT id FROM timer WHERE state='pending' AND fire_at <= now() "
        "ORDER BY fire_at FOR UPDATE SKIP LOCKED LIMIT :k"), {"k": limit})).all()
    n = 0
    for (timer_id,) in rows:
        try:
            await _fire_one(s, timer_id)
            n += 1
        except Exception as exc:  # never silent — dead-letter + log
            await _record_failed(s, timer_id, exc)
            n += 1
    return n


async def _fire_one(s: AsyncSession, timer_id) -> None:
    """Load the timer and dispatch per `Timer.type`, then mark it fired.

    Spine functions may still be stubs in this slice; any raise is caught by
    `tick` and routed to `_record_failed`. Wrapped in a SAVEPOINT so a failure
    here cannot poison the surrounding session.
    """
    async with s.begin_nested():
        timer = await s.get(Timer, timer_id)
        if timer.type in ("accept_window", "fulfilment_sla"):
            spine.on_stall(s, timer)
        elif timer.type == "supervisor_sla":
            spine.apply_recommendation(
                s, timer.escalation_id, outcome="auto_proceeded")
        elif timer.type == "backstop_cycle":
            spine.hard_escalate(s, timer)
        timer.state = "fired"


async def _record_failed(s: AsyncSession, timer_id, exc: Exception) -> None:
    """Dead-letter a failed transition and log it — never silent.

    `_fire_one` runs inside its own SAVEPOINT, so a raised exception only
    rolls that nested transaction back; the surrounding session stays usable
    for this insert.
    """
    log.exception("timer %s failed to fire", timer_id)
    s.add(FailedTransition(timer_id=timer_id, error=repr(exc)))
    await s.flush()
