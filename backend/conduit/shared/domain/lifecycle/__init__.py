"""Lifecycle package — per-entity pure machines + the C4 orchestrator.

C3 converted the single-file ``lifecycle.py`` into this package: each entity
(child / workorder / escalation / glitch) is a PURE submodule exposing a
``_LEGAL: dict[str, set[str]]`` and ``legal(frm, to) -> bool`` (no DB, no I/O).

C4 generalises ``transition()`` into the single writer path (Spec §7.2):
validate legality (else ``ConflictError``), apply the state change, append
EXACTLY ONE ``event``+detail via the merged writer, arm/cancel ``Timer`` rows,
and perform cross-entity hops — all in the caller's session, in ONE
transaction. ``transition`` itself NEVER commits (services flush; the API
commits at the edge).

Back-compat is mandatory. The merged consumers
(``conduit.guest.services.intake / nodispatch / smalltalk`` and
``tests/spine/test_lifecycle.py``) do
``from conduit.shared.domain import lifecycle`` then call
``lifecycle.transition(s, child, to, actor_account_id=..., ...)`` /
``lifecycle.ChildState``. For a ``ChildSubRequest`` subject moving to a
LEGACY state (triaged/answered/concierge_queue/closed/reopened) the behaviour
is byte-identical to the merged code: same legality guard (``child._LEGAL``),
the same single ``writer.emit_child`` call with the same event-type mapping
(``_EVENT``), the same ``ConflictError`` idiom, and the same flush discipline
(``emit_child`` flushes for the Event id; ``transition`` adds no extra flush
and never commits).
"""
from __future__ import annotations

import datetime as dt

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from conduit.core.exceptions import ConflictError
from conduit.shared.events import writer
from conduit.shared.models import (ChildSubRequest, CrossDeptNotification,
                                   Escalation, Glitch, IssueCode, SLAPreset,
                                   WorkOrder)

from . import child as child
from . import escalation as escalation
from . import glitch as glitch
from . import workorder as workorder
from .child import ChildState as ChildState

# Preserved from the merged ``lifecycle.py`` — the legacy child event-type
# mapping. UNCHANGED (back-compat: intake/nodispatch/smalltalk +
# test_lifecycle.py). The legal map is sourced from the moved child machine
# (superset of the old map).
_LEGAL = child._LEGAL
_EVENT = {
    "triaged": "child_triaged",
    "answered": "child_answered",
    "concierge_queue": "child_deferred",
    "closed": "child_closed",
    "reopened": "child_reopened",
}

# Dispatch-arc child states (added by the A5 widening) map to the new C4
# child event types — emitted via the new ``writer.emit_child_*`` helpers,
# NOT via the legacy ``emit_child``/``_EVENT`` path (kept byte-identical).
_CHILD_NEW_EMIT = {
    "routing": writer.emit_child_routed,
    "done_pending_confirm": writer.emit_child_done_pending_confirm,
    "cancelled": writer.emit_child_cancelled,
}

_WO_EMIT = {
    "created": writer.emit_work_order_created,
    "pushed": writer.emit_work_order_pushed,
    "broadcast": writer.emit_work_order_broadcast,
    "accepted": writer.emit_work_order_accepted,
    "in_progress": writer.emit_work_order_in_progress,
    "completed": writer.emit_work_order_completed,
    "cancelled": writer.emit_work_order_cancelled,
}

# Escalation/Glitch resolve once; one event per terminal disposition.
_ESC_RESOLVED = {"approved", "edited", "overridden", "auto_proceeded",
                 "hard_escalated"}
_GLITCH_CLOSED = {"closed", "auto_closed"}

# Timer defaults (D23) — used only when neither the child's issue-code
# SLAPreset nor an explicit ctx override supplies a duration. Named so no
# magic number is hardcoded inline.
DEFAULT_ACCEPT_WINDOW_SECONDS = 300
DEFAULT_FULFILMENT_SLA_SECONDS = 3600

__all__ = [
    "ChildState",
    "child",
    "workorder",
    "escalation",
    "glitch",
    "transition",
]


def _machine_for(subject):
    if isinstance(subject, ChildSubRequest):
        return child
    if isinstance(subject, WorkOrder):
        return workorder
    if isinstance(subject, Escalation):
        return escalation
    if isinstance(subject, Glitch):
        return glitch
    raise ConflictError(f"no lifecycle machine for {type(subject).__name__}")


async def _sla_for_child(s: AsyncSession, child_row: ChildSubRequest):
    """Resolve the child's issue-code SLAPreset, if any (D23 durations)."""
    if child_row.issue_code_id is None:
        return None
    ic = (await s.execute(sa.select(IssueCode)
          .where(IssueCode.id == child_row.issue_code_id))).scalar_one_or_none()
    if ic is None or ic.sla_preset_id is None:
        return None
    return (await s.execute(sa.select(SLAPreset)
            .where(SLAPreset.id == ic.sla_preset_id))).scalar_one_or_none()


async def transition(s: AsyncSession, subject, to: str, *,
                      actor=None, actor_account_id=None,
                      resolution_child_id=None, **ctx) -> None:
    """The ONLY writer path (Spec §7.2).

    Validate legality (else ``ConflictError`` — and NOTHING is written before
    the guard, so an illegal transition is side-effect-free), apply the state
    change, append EXACTLY ONE ``event``+detail via the merged writer,
    arm/cancel ``Timer`` rows, and perform the §7.2 cross-entity hops — all in
    the caller's session, in ONE transaction. Never commits.

    Back-compat: ``actor`` and ``actor_account_id`` are equivalent; the
    legacy ``ChildSubRequest`` path (legacy target states) is byte-identical
    to the merged ``lifecycle.py`` (same guard, same single ``emit_child``,
    same flush discipline).
    """
    actor_id = actor_account_id
    if actor_id is None and actor is not None:
        actor_id = getattr(actor, "id", actor)

    machine = _machine_for(subject)

    # Guard FIRST — nothing written/flushed before this, so an illegal
    # transition has ZERO side effects (back-compat: same error idiom).
    if not machine.legal(subject.state, to):
        raise ConflictError(f"illegal transition {subject.state}->{to}")

    subject.state = to
    s.add(subject)

    # --- exactly ONE event + detail ------------------------------------------
    if isinstance(subject, ChildSubRequest):
        if to in _EVENT:
            # Legacy child path — byte-identical to the merged code.
            await writer.emit_child(s, _EVENT[to], subject.id, actor_id,
                                    resolution_child_id=resolution_child_id)
        else:
            await _CHILD_NEW_EMIT[to](s, subject.id, actor_id)
    elif isinstance(subject, WorkOrder):
        await _WO_EMIT[to](s, subject.id, actor_id)
    elif isinstance(subject, Escalation):
        if to in _ESC_RESOLVED:
            await writer.emit_escalation_resolved(s, subject.id, actor_id)
        else:
            await writer.emit_escalation_opened(s, subject.id, actor_id)
    elif isinstance(subject, Glitch):
        if to in _GLITCH_CLOSED:
            await writer.emit_glitch_closed(s, subject.id, actor_id)
        else:
            await writer.emit_glitch_opened(s, subject.id, actor_id)

    # --- timers + cross-entity hops (one txn, caller's session, no commit) ---
    if isinstance(subject, ChildSubRequest):
        await _child_hops(s, subject, to, actor_id, ctx)
    elif isinstance(subject, WorkOrder):
        await _workorder_hops(s, subject, to, actor_id, ctx)
    elif isinstance(subject, Escalation):
        await _escalation_hops(s, subject, to, actor_id, ctx)


async def _child_hops(s: AsyncSession, child_row: ChildSubRequest, to: str,
                       actor_id, ctx: dict) -> None:
    """child ``routing`` ⇒ create the WorkOrder + arm accept_window &
    fulfilment_sla timers (D23/§7.2). Durations: the child's issue-code
    SLAPreset, else an explicit ctx override, else the named defaults."""
    if to != "routing":
        return
    # Selection/ctx supplies the WorkOrder shape; routing RULES are NOT
    # re-implemented here (C1 ``routing.select`` owns them — call it upstream
    # and pass the resolved Selection via ctx).
    sel = ctx.get("selection")
    kind = ctx.get("kind", "dispatch")
    routing_model = ctx.get(
        "routing_model",
        getattr(sel, "section_id", None) is not None and "section_pooled"
        or "section_pooled")
    priority_tier = ctx.get("priority_tier") or child_row.priority_tier or "P3"
    wo = WorkOrder(
        child_id=child_row.id, kind=kind, routing_model=routing_model,
        priority_tier=priority_tier,
        assigned_servicer_id=getattr(sel, "assigned_id", None),
        accountable_owner_id=getattr(sel, "accountable_id", None),
        section_id=getattr(sel, "section_id", None),
        queue_position=getattr(sel, "queue_position", None),
        state="created")
    s.add(wo)
    await s.flush()
    await writer.emit_work_order_created(s, wo.id, actor_id)

    sla = await _sla_for_child(s, child_row)
    accept_secs = (ctx.get("accept_window_seconds")
                   or (sla.accept_window_seconds if sla else None)
                   or DEFAULT_ACCEPT_WINDOW_SECONDS)
    fulfil_secs = (ctx.get("fulfilment_sla_seconds")
                   or (sla.fulfilment_sla_seconds if sla else None)
                   or DEFAULT_FULFILMENT_SLA_SECONDS)

    # DB now() is the time source (AD5/D23): compute fire_at server-side.
    now = (await s.execute(sa.select(sa.func.now()))).scalar_one()
    from conduit.shared.engine.timers import TimerType, arm
    await arm(s, "child_id", child_row.id, TimerType.ACCEPT_WINDOW,
              fire_at=now + dt.timedelta(seconds=accept_secs))
    await arm(s, "child_id", child_row.id, TimerType.FULFILMENT_SLA,
              fire_at=now + dt.timedelta(seconds=fulfil_secs))


async def _workorder_hops(s: AsyncSession, wo: WorkOrder, to: str,
                           actor_id, ctx: dict) -> None:
    """WorkOrder ⇒ completed (§7.2/D14): linked child → done_pending_confirm
    (via the same ``transition`` so its event is emitted too); if the issue
    code declares a downstream department (it has no such column today, so
    fall back to ``ctx['target_department']``) ⇒ emit a CrossDeptNotification.
    WorkOrder accept ⇒ cancel the accept_window timer (D23)."""
    from conduit.shared.engine.timers import cancel_for

    if to == "accepted":
        await cancel_for(s, "child_id", wo.child_id)
        return
    if to != "completed":
        return

    child_row = (await s.execute(sa.select(ChildSubRequest)
                 .where(ChildSubRequest.id == wo.child_id))).scalar_one()
    # Move the linked child through the SAME orchestrator (its event +
    # any further hops emit consistently). Only when legal — a child not on
    # the dispatch arc (e.g. already terminal) is left untouched.
    if child.legal(child_row.state, "done_pending_confirm"):
        await transition(s, child_row, "done_pending_confirm",
                          actor_account_id=actor_id)

    # Downstream department: IssueCode has no "downstream dept" column today,
    # so this hop fires only when ctx explicitly provides one.
    target_dept = ctx.get("target_department")
    if target_dept is not None:
        xdn = CrossDeptNotification(
            source_work_order_id=wo.id,
            target_department=target_dept,
            child_id=wo.child_id,
            reason=ctx.get("xdn_reason", "work_order_completed"))
        s.add(xdn)
        await s.flush()
        await writer.emit_cross_dept_notified(s, xdn.id, actor_id)


async def _escalation_hops(s: AsyncSession, esc: Escalation, to: str,
                            actor_id, ctx: dict) -> None:
    """Escalation resolved with a relocate action (§7.2): call the REAL
    merged stay/binding ``relocate_stay`` seam (re-bind — NOT reimplemented
    here), then close the linked Glitch through the same orchestrator.

    The relocate inputs (``stay_id`` + ``new_room_id``) are Phase-E wiring
    (resolving the escalation's stay/recommendation target is not yet a built
    surface). When they are supplied via ctx the real seam is invoked; the
    glitch-close hop always runs when a linked Glitch exists. See REPORT.
    """
    if to not in _ESC_RESOLVED:
        return
    action = ctx.get("action") or ctx.get("resolution_action")
    if action == "relocate":
        stay_id = ctx.get("stay_id")
        new_room_id = ctx.get("new_room_id")
        if stay_id is not None and new_room_id is not None:
            # Real merged seam (do NOT reimplement re-binding):
            # conduit.supervisor.services.stays.relocate_stay(
            #     s, stay_id, new_room_id, *, actor)
            from conduit.supervisor.services.stays import relocate_stay
            await relocate_stay(s, stay_id, new_room_id,
                                actor=ctx.get("actor"))
        # Close the linked Glitch (the recovery the relocate discharges).
        gl = (await s.execute(sa.select(Glitch)
              .where(Glitch.child_id == esc.child_id))).scalar_one_or_none()
        if gl is not None and glitch.legal(gl.state, "closed"):
            await transition(s, gl, "closed", actor_account_id=actor_id)
