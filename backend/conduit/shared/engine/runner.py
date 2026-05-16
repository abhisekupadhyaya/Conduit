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

from conduit.core.config import get_settings

log = logging.getLogger("conduit.engine")


async def run_engine(stop: asyncio.Event) -> None:
    s = get_settings()
    if not s.engine_enabled:
        log.info("engine disabled (CONDUIT_ENGINE_ENABLED=false)")
        return
    log.info("engine started; poll=%ss", s.engine_poll_seconds)
    while not stop.is_set():
        try:
            await _tick()
        except Exception:  # never let one bad tick kill the loop
            log.exception("engine tick failed")
        try:
            await asyncio.wait_for(stop.wait(), timeout=s.engine_poll_seconds)
        except TimeoutError:
            pass
    log.info("engine stopped")


async def _tick() -> None:
    """Claim & fire due timers. Implemented once the `timer` model lands.

    SELECT ... WHERE state='pending' AND fire_at <= now()
    FOR UPDATE SKIP LOCKED  → fire → append event → commit.
    """
    return None
