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

        # Spawn the front-office "guest move" task (spec §7.3 / decisions 5a &
        # 2). EXACTLY ONE per relocate resolution — only when a relocate
        # actually occurred (stay_id + new_room_id supplied → real re-bind
        # above). Reuses the triggering child's Request (decision 5a: lineage
        # via ``predecessor_child_id`` — its first real consumer; NO synthetic
        # Request / fake guest account). Routed through the EXISTING C4 routing
        # path (``_child_hops`` builds the WorkOrder + arms timers — NOT
        # reimplemented here); the move WO carries the legible
        # ``kind='relocation_move'`` (decision 2).
        if stay_id is not None and new_room_id is not None:
            await _spawn_relocation_move_task(s, esc, actor_id)


async def _spawn_relocation_move_task(s: AsyncSession, esc: Escalation,
                                       actor_id) -> None:
    """Spawn the front-office guest-move ChildSubRequest + its
    ``relocation_move`` WorkOrder for a just-executed relocate (spec §7.3 /
    §4 decisions 5a & 2).

    The new child REUSES the triggering child's ``request_id`` (decision 5a —
    no synthetic Request, no fake guest account) and records lineage via
    ``predecessor_child_id`` (its first real consumer). It is created at
    ``triaged`` so the EXISTING child machine edge ``triaged -> routing`` and
    the EXISTING C4 routing hop (``_child_hops``) build the WorkOrder + arm
    its timers — routing is NOT reimplemented here: C1 ``routing.select`` owns
    the allocation rule and is CALLED over an engine-local candidate read
    (the established ``_route_dispatch_child`` idiom), then the resolved pure
    Selection is passed into ``transition(child, 'routing', ...)``. The WO is
    advanced to ``pushed``/``broadcast`` through the SAME C4 writer path so it
    appears on the existing servicer queue. Exactly one append-only event per
    transition (inherited)."""
    from conduit.shared.domain import routing
    from conduit.shared.models import (Request, Room, RosterAssignment,
                                        Section, StaffProfile, StaffSkill)
    from conduit.shared.models import Roster as _Roster
    from conduit.shared.models import Stay as _Stay

    # The triggering child → its request_id (decision 5a: reuse the Request).
    trigger = (await s.execute(
        sa.select(ChildSubRequest)
        .where(ChildSubRequest.id == esc.child_id))).scalar_one_or_none()
    if trigger is None:
        return

    # The seeded system FO-GUEST-MOVE issue code (B1; origin='system',
    # dispatch). Idempotent lookup idiom used across the codebase.
    fo_ic = (await s.execute(
        sa.select(IssueCode).where(
            sa.func.lower(IssueCode.code) == "fo-guest-move",
            IssueCode.status == "active"))).scalars().first()
    if fo_ic is None:
        return

    # ONE move child reusing the triggering child's Request; lineage via
    # ``predecessor_child_id``. Created ``triaged`` so the EXISTING
    # ``triaged -> routing`` edge + C4 routing hop drive it like a normal
    # dispatch child. Required NOT-NULL/no-default fields: request_id / text /
    # outcome (state defaults to intake → set triaged explicitly).
    move_child = ChildSubRequest(
        request_id=trigger.request_id,
        predecessor_child_id=trigger.id,
        text="Guest move: relocate the guest to the new room.",
        outcome="auto",
        issue_code_id=fo_ic.id,
        fulfilment_mode="dispatch",
        state="triaged",
        priority_tier=trigger.priority_tier or "P3")
    s.add(move_child)
    await s.flush()

    # Resolve the owning Section via child → Request → Stay → Room → Section
    # (the relocated stay's NEW room → its section) — the established
    # ``_route_dispatch_child`` engine-local read (services/engine may read;
    # routing RULES stay in C1 ``routing.select``).
    sec_row = (await s.execute(
        sa.select(Section.id, Section.property_id)
        .select_from(Request)
        .join(_Stay, _Stay.id == Request.stay_id)
        .join(Room, Room.id == _Stay.room_id)
        .join(Section, Section.id == Room.section_id)
        .where(Request.id == move_child.request_id))).first()
    section_id = sec_row[0] if sec_row else None
    property_id = sec_row[1] if sec_row else None

    model = (routing.RoutingModel.SECTION_POOLED
             if fo_ic.routing_model == "section_pooled"
             else routing.RoutingModel.SKILL_MATCHED)

    # Engine-local candidate read (the exact ``_route_dispatch_child`` shape):
    # rosters → assignments → owner ids → skills → StaffProfile candidates.
    # Routing rules are NOT re-implemented — C1 ``routing.select`` decides.
    rosters = {
        r.id: r for r in (await s.execute(
            sa.select(_Roster).where(_Roster.property_id == property_id)
        )).scalars().all()
    }
    owner_ids: set = set()
    assigns: dict = {}
    if rosters:
        for a in (await s.execute(
            sa.select(RosterAssignment)
            .where(RosterAssignment.roster_id.in_(list(rosters)))
        )).scalars().all():
            a.roster = rosters.get(a.roster_id)
            assigns.setdefault(a.account_id, []).append(a)
            if (a.assignment == "owner" and a.status == "active"
                    and a.section_id == section_id):
                owner_ids.add(a.account_id)
    skills: dict = {}
    if assigns:
        for sk in (await s.execute(
            sa.select(StaffSkill)
            .where(StaffSkill.account_id.in_(list(assigns)))
        )).scalars().all():
            skills.setdefault(sk.account_id, []).append(sk.skill)
    candidates = []
    for prof in (await s.execute(
        sa.select(StaffProfile)
        .where(StaffProfile.account_id.in_(list(assigns) or [None]))
    )).scalars().all():
        candidates.append(routing.Candidate(
            account_id=prof.account_id, profile=prof,
            assignments=assigns.get(prof.account_id, []),
            skills=tuple(skills.get(prof.account_id, ())),
            is_section_owner=prof.account_id in owner_ids,
            in_zone=True))

    now = (await s.execute(sa.select(sa.func.now()))).scalar_one()
    sel = routing.select(model=model, candidates=candidates, now=now,
                         section_id=section_id)

    # The EXISTING C4 routing hop (``_child_hops``) creates the WorkOrder +
    # arms accept_window/fulfilment_sla timers — NOT reimplemented here. The
    # legible ``kind='relocation_move'`` (decision 2) rides via ctx.
    await transition(
        s, move_child, "routing", actor_account_id=actor_id,
        selection=sel, kind="relocation_move",
        routing_model=fo_ic.routing_model,
        priority_tier=move_child.priority_tier)
    await s.flush()

    # Advance the freshly-created WorkOrder to pushed/broadcast through the
    # SAME C4 writer path (the established ``_route_dispatch_child`` tail —
    # assigned ⇒ pushed to the owner; else claim-fallback broadcast). The
    # dispatch leg's state lives on the WorkOrder; the child stays at routing.
    move_wo = (await s.execute(
        sa.select(WorkOrder)
        .where(WorkOrder.child_id == move_child.id))).scalar_one()
    nxt = "pushed" if sel.assigned_id is not None else "broadcast"
    await transition(s, move_wo, nxt, actor_account_id=actor_id)
