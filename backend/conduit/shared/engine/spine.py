"""The escalation spine (D9/D10/D20/D21).

Three triggers produce an AI recommendation for the supervisor decision
queue: triage-flag (D5/D24), stall (D10/D23), servicer-raised mid-lifecycle
escalation (D20). The supervisor approves/edits/overrides; silence past the
supervisor-SLA → AI auto-proceeds (D9). Bounded: after N cycles → hard-escalate
to the non-time-boxed duty manager (D21). The human never gets a blank ticket
(D7).

``open_escalation`` (Spec §7.4) is the only built surface here. It is
``shared/engine`` (not pure domain), so engine-local reads off the caller's
session are allowed; routing rules (C1) and recommendation rules (C2) are
NEVER re-implemented — they are called. Effecting goes through the C4
new-entity emission pattern (instantiate the row, ``flush`` for its id, emit
EXACTLY ONE event via ``shared.events.writer`` — the same hop the C4
orchestrator uses to create a WorkOrder in ``_child_hops``) and
``timers.arm``. One transaction, the caller's session, NO commit.
"""
from __future__ import annotations

import datetime as dt
from enum import Enum

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from conduit.core.exceptions import ConflictError
from conduit.shared.domain import recommendation, routing
from conduit.shared.events import writer
from conduit.shared.models import (ChildSubRequest, Escalation, IssueCode,
                                   RecApprove, RecBroadcast, RecDeny,
                                   RecExtendSla, RecReassign, RecRelocate,
                                   Recommendation, Request, Room, Roster,
                                   RosterAssignment, Section, SLAPreset,
                                   StaffProfile, Stay)
from conduit.shared.models import EscalationLadder as _EscalationLadder

# Named fallback (D9) — used ONLY when the active SLAPreset chain is genuinely
# absent for the child's tier; never an inline magic number.
DEFAULT_SUPERVISOR_SLA_SECONDS = 900

# Action → its thin ``rec_*`` detail row, built from ``draft.params`` (the C2
# RecommendationDraft). Keyed by the exact ck_rec_action vocabulary.
_REC_DETAIL = {
    "reassign": lambda eid, p: RecReassign(
        recommendation_escalation_id=eid,
        target_account_id=p["target_account_id"]),
    "broadcast": lambda eid, p: RecBroadcast(
        recommendation_escalation_id=eid),
    "relocate": lambda eid, p: RecRelocate(
        recommendation_escalation_id=eid,
        target_room_id=p["target_room_id"]),
    "extend_sla": lambda eid, p: RecExtendSla(
        recommendation_escalation_id=eid,
        extend_seconds=p["extend_seconds"]),
    "approve": lambda eid, p: RecApprove(recommendation_escalation_id=eid),
    "deny": lambda eid, p: RecDeny(recommendation_escalation_id=eid),
}


class EscalationTrigger(str, Enum):
    TRIAGE_FLAG = "triage_flag"
    STALL = "stall"
    SERVICER_RAISED = "servicer_raised"


async def _property_id_for_child(s: AsyncSession,
                                 child: ChildSubRequest):
    """Resolve the child's owning property via the real FK chain
    child→Request→Stay→Room→Section→Property (engine-local read)."""
    pid = (await s.execute(
        sa.select(Section.property_id)
        .select_from(Request)
        .join(Stay, Stay.id == Request.stay_id)
        .join(Room, Room.id == Stay.room_id)
        .join(Section, Section.id == Room.section_id)
        .where(Request.id == child.request_id)
    )).scalar_one_or_none()
    return pid


async def _sla_for_child(s: AsyncSession, child: ChildSubRequest):
    """The child's issue-code SLAPreset (the §7.4 duration source)."""
    if child.issue_code_id is None:
        return None
    ic = (await s.execute(
        sa.select(IssueCode).where(IssueCode.id == child.issue_code_id)
    )).scalar_one_or_none()
    if ic is None or ic.sla_preset_id is None:
        return None
    return (await s.execute(
        sa.select(SLAPreset).where(SLAPreset.id == ic.sla_preset_id)
    )).scalar_one_or_none()


async def _stall_candidates(s: AsyncSession, property_id):
    """Engine-local read of property staff as routing ``Candidate`` rows.

    Routing RULES are NOT re-implemented — these feed C1 ``routing.select``.
    RosterAssignment has no ``.roster`` ORM relationship (modelled FK-only);
    we attach the Roster as a plain attribute so the pure availability
    contract (``assignment.roster``) holds — the established repo idiom
    (servicer/dal/self.py, supervisor/dal/staff.py)."""
    rosters = {
        r.id: r for r in (await s.execute(
            sa.select(Roster).where(Roster.property_id == property_id)
        )).scalars().all()
    }
    roster_ids = list(rosters)
    assigns: dict = {}
    if roster_ids:
        for a in (await s.execute(
            sa.select(RosterAssignment)
            .where(RosterAssignment.roster_id.in_(roster_ids))
        )).scalars().all():
            a.roster = rosters.get(a.roster_id)
            assigns.setdefault(a.account_id, []).append(a)

    candidates = []
    for prof in (await s.execute(
        sa.select(StaffProfile)
        .where(StaffProfile.account_id.in_(list(assigns) or [None]))
    )).scalars().all():
        candidates.append(routing.Candidate(
            account_id=prof.account_id,
            profile=prof,
            assignments=assigns.get(prof.account_id, []),
        ))
    return candidates


async def _assemble_context(s: AsyncSession, child: ChildSubRequest,
                            trigger: EscalationTrigger, property_id,
                            ctx: dict) -> dict:
    """Build the pure, already-fetched ``context`` C2 ``recommendation.build``
    consumes — one branch per trigger (Spec §7.4)."""
    if trigger is EscalationTrigger.STALL:
        # §7.4: reassign target = C1 routing.select EXCLUDING the stalled
        # assignee. routing OWNS the rule; the spine only excludes + reads.
        stalled = ctx.get("stalled_account_id")
        exclude = {stalled} if stalled is not None else set()
        now = (await s.execute(sa.select(sa.func.now()))).scalar_one()
        sel = routing.select(
            model=routing.RoutingModel.SKILL_MATCHED,
            candidates=await _stall_candidates(s, property_id),
            now=now, exclude=exclude)
        return {"reassign_target": sel.assigned_id,
                "broadcast_pool": sel.broadcast_pool}

    if trigger is EscalationTrigger.SERVICER_RAISED:
        # §7.4: relocate to a deterministic available room if one is found,
        # else extend the SLA by the child's fulfilment window.
        sla = await _sla_for_child(s, child)
        extend = (sla.fulfilment_sla_seconds if sla is not None
                  else DEFAULT_SUPERVISOR_SLA_SECONDS)
        return {"available_room_id": ctx.get("available_room_id"),
                "extend_seconds": extend}

    # triage_flag — the flag verdict (D5/D24).
    return {"verdict": ctx.get("verdict")}


async def open_escalation(s: AsyncSession, child: ChildSubRequest,
                          trigger, **ctx) -> Escalation:
    """Open a decision-queue item with an AI-prepared recommendation
    (Spec §7.4). One transaction, the caller's session, NO commit.

    Creates an ``Escalation(open)`` linked to the child, builds the
    deterministic recommendation via C2 (routing rules via C1 for stall),
    persists the ``Recommendation`` + its matching ``rec_*`` detail, emits
    EXACTLY ONE ``escalation_opened`` and ONE ``recommendation_created`` event
    through the writer (the C4 new-entity hop pattern), and arms a
    ``supervisor_sla`` ``Timer`` whose ``fire_at`` is DB ``now()`` plus the
    active SLAPreset's ``supervisor_sla_seconds`` (the issue-code → SLAPreset
    chain), gated by the property's active ``EscalationLadder``.
    """
    trig = trigger.value if isinstance(trigger, EscalationTrigger) else trigger

    property_id = await _property_id_for_child(s, child)
    if property_id is None:
        raise ConflictError(
            f"child {child.id} has no resolvable property (stay chain)")

    # §7.4: the escalation spine is gated by the property's active ladder
    # (D21 — the non-time-boxed duty manager backstop lives there).
    ladder = (await s.execute(
        sa.select(_EscalationLadder).where(
            _EscalationLadder.property_id == property_id,
            _EscalationLadder.status == "active")
    )).scalar_one_or_none()
    if ladder is None:
        raise ConflictError(
            f"no active EscalationLadder for property {property_id}")

    actor_id = ctx.get("actor_account_id")

    # --- Escalation(open) — C4 new-entity emission pattern (mirrors the
    # WorkOrder-creation hop in lifecycle._child_hops): instantiate, flush
    # for the id, emit EXACTLY ONE event via the writer. ``transition`` is
    # NOT used: the escalation machine has no ``*->open`` legal edge (``open``
    # is the server_default start state, not a transition). No second writer
    # path is invented.
    esc = Escalation(child_id=child.id, trigger=trig,
                     raised_by_account_id=actor_id)
    s.add(esc)
    await s.flush()
    await writer.emit_escalation_opened(s, esc.id, actor_id)

    # --- Recommendation via the PURE C2 build (routing rules via C1) -------
    context = await _assemble_context(s, child, (
        trigger if isinstance(trigger, EscalationTrigger)
        else EscalationTrigger(trig)), property_id, ctx)
    draft = recommendation.build(trigger=trig, child=child, context=context)

    s.add(Recommendation(escalation_id=esc.id, action=draft.action,
                          rationale_text=draft.rationale_text))
    await s.flush()
    s.add(_REC_DETAIL[draft.action](esc.id, draft.params))
    await writer.emit_recommendation_created(s, esc.id, actor_id)

    # --- supervisor_sla Timer (D9). Duration: the child's issue-code
    # SLAPreset (tier chain), else the NAMED fallback. fire_at uses DB now()
    # (AD5), never the host clock.
    sla = await _sla_for_child(s, child)
    supervisor_secs = (sla.supervisor_sla_seconds if sla is not None
                       else DEFAULT_SUPERVISOR_SLA_SECONDS)
    now = (await s.execute(sa.select(sa.func.now()))).scalar_one()
    from conduit.shared.engine.timers import TimerType, arm
    await arm(s, "escalation_id", esc.id, TimerType.SUPERVISOR_SLA,
              fire_at=now + dt.timedelta(seconds=supervisor_secs))

    return esc


def auto_proceed(escalation_id: str) -> None:
    """Supervisor silent past SLA → proceed on the recommendation (D9),
    unless the D21 bound is hit → hard-escalate the duty manager."""
    raise NotImplementedError
