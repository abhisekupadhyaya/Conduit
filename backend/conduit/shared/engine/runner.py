"""The lifecycle engine — in-process poll loop (AD4/AD5).

Runs inside the API process (single deployable). DB-backed timers: every tick
it claims due timers with `FOR UPDATE SKIP LOCKED` (so a second instance never
double-fires) and applies the transition + appends the event in one
transaction. Crash-safe: a restart simply resumes everything already due —
this is what keeps "nothing silently lost" true on cheap single-instance infra.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import logging

import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from conduit.core.config import get_settings
from conduit.shared.db import SessionLocal
from conduit.shared.engine import spine
from conduit.shared.events import writer
from conduit.shared.models import (ChildSubRequest, Escalation,
                                   FailedTransition, Timer, WorkOrder)

log = logging.getLogger("conduit.engine")

# D22 — on a STALL the guest is proactively told "running late". The child's
# ``revised_eta`` is pushed out by this NAMED grace offset from DB ``now()``
# (AD5 time source). Never an inline magic number. Used only when the child's
# issue-code SLAPreset does not cleanly supply a fulfilment window to derive
# from (preferred when available — a sane, spec-faithful "running late" hint).
REVISED_ETA_GRACE_SECONDS = 1800


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


async def _child_for_timer(s: AsyncSession,
                           timer: Timer) -> ChildSubRequest | None:
    """Resolve the stall subject CHILD from the timer's typed FK (Spec §7.3).

    C4 ``lifecycle._child_hops`` arms ``accept_window``/``fulfilment_sla`` on
    ``child_id`` — that is the primary path. Fall back through
    ``work_order_id`` → ``WorkOrder.child_id`` if a timer is ever armed on the
    WorkOrder instead (reconcile in the runner WITHOUT changing C4/spine)."""
    if timer.child_id is not None:
        return await s.get(ChildSubRequest, timer.child_id)
    if timer.work_order_id is not None:
        wo = await s.get(WorkOrder, timer.work_order_id)
        if wo is not None:
            return await s.get(ChildSubRequest, wo.child_id)
    return None


async def _revised_eta(s: AsyncSession, child: ChildSubRequest):
    """D22 "running late" hint: DB ``now()`` (AD5) + a sane window.

    Prefer deriving the window from the child's issue-code SLAPreset's
    ``fulfilment_sla_seconds`` (the same chain the spine/lifecycle use); fall
    back to the NAMED ``REVISED_ETA_GRACE_SECONDS`` when that chain is absent —
    never an inline magic number."""
    secs = REVISED_ETA_GRACE_SECONDS
    sla = await spine._sla_for_child(s, child)
    if sla is not None and sla.fulfilment_sla_seconds:
        secs = sla.fulfilment_sla_seconds
    now = (await s.execute(sa.select(sa.func.now()))).scalar_one()
    return now + dt.timedelta(seconds=secs)


async def _fire_one(s: AsyncSession, timer_id) -> None:
    """Load the timer, resolve its typed subject OBJECT, dispatch to the spine
    per `Timer.type` (Spec §7.3), then mark it fired.

    Interface-mismatch reconciliation (mandatory): D1/D2 spine functions take
    the actual ORM OBJECT (``open_escalation(s, child, ...)`` /
    ``apply_recommendation(s, escalation, ...)`` / ``hard_escalate(s,
    escalation)``). B2 passed the timer/escalation_id. D3 loads the real row
    from the Timer's typed subject FK and passes the OBJECT — D1/D2 signatures
    are UNCHANGED (spec-reviewed); only the runner adapts.

    Wrapped in a SAVEPOINT so a failure here (e.g. spine ``ConflictError``)
    rolls back ONLY this nested transaction; `tick` catches it and routes to
    `_record_failed`, and the claim loop survives (B2 behaviour preserved).
    The SAVEPOINT is managed explicitly (begin / commit / rollback) rather
    than via ``async with`` — identical nested-transaction semantics, but it
    does not trip the ``TransactionalContext`` guard when an outer
    savepoint-restart listener (the test harness) reacts to the nested
    transaction ending mid-context. B2's intent ("a failure here cannot poison
    the surrounding session") is preserved exactly.
    """
    sp = await s.begin_nested()
    try:
        timer = await s.get(Timer, timer_id)
        if timer.type in ("accept_window", "fulfilment_sla"):
            # STALL → open the escalation through the spine with the CHILD
            # object, and proactively push the guest's revised_eta (D22).
            child = await _child_for_timer(s, timer)
            if child is None:
                raise spine.ConflictError(
                    f"timer {timer.id} ({timer.type}) has no resolvable child")
            await spine.open_escalation(s, child, "stall")
            child.revised_eta = await _revised_eta(s, child)
            s.add(child)
        elif timer.type == "supervisor_sla":
            # D9 silence ≡ approve auto-proceed with the Escalation OBJECT.
            # D2 enforces the D21 bound internally (may hard-escalate).
            escalation = await s.get(Escalation, timer.escalation_id)
            if escalation is None:
                raise spine.ConflictError(
                    f"timer {timer.id} (supervisor_sla) has no escalation")
            await spine.apply_recommendation(
                s, escalation, outcome="auto_proceeded")
        elif timer.type == "backstop_cycle":
            # D21 backstop → the non-time-boxed duty manager.
            escalation = await s.get(Escalation, timer.escalation_id)
            if escalation is None:
                raise spine.ConflictError(
                    f"timer {timer.id} (backstop_cycle) has no escalation")
            await spine.hard_escalate(s, escalation)
        timer.state = "fired"
        # C4-added writer emit (Spec §7.3). B2 only set state; D3 prefers the
        # single C4 writer fn now that it exists — one event per transition.
        await writer.emit_timer_fired(s, timer.id)
    except BaseException:
        # Roll the SAVEPOINT back so a spine failure cannot poison the
        # surrounding session; re-raise so `tick` dead-letters via
        # `_record_failed` and the claim loop survives (B2 invariant).
        await sp.rollback()
        raise
    else:
        await sp.commit()


async def _record_failed(s: AsyncSession, timer_id, exc: Exception) -> None:
    """Dead-letter a failed transition and log it — never silent.

    `_fire_one` runs inside its own SAVEPOINT, so a raised exception only
    rolls that nested transaction back; the surrounding session stays usable
    for this insert.
    """
    log.exception("timer %s failed to fire", timer_id)
    s.add(FailedTransition(timer_id=timer_id, error=repr(exc)))
    await s.flush()
