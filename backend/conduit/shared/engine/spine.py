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
from conduit.shared.domain import lifecycle, recommendation, routing
from conduit.shared.events import writer
from conduit.shared.models import (ChildSubRequest, Escalation, IssueCode,
                                   NoDispatchResolution,
                                   RecApplyReservationMutation, RecApprove,
                                   RecBroadcast, RecDeny, RecExtendSla,
                                   RecReassign, RecRelocate, Recommendation,
                                   Request, Room, Roster, RosterAssignment,
                                   Section, SLAPreset, StaffProfile, Stay,
                                   WorkOrder)
from conduit.shared.models import EscalationLadder as _EscalationLadder

# Named fallback (D9) — used ONLY when the active SLAPreset chain is genuinely
# absent for the child's tier; never an inline magic number.
DEFAULT_SUPERVISOR_SLA_SECONDS = 900

# D1 fix: derive the C1 routing model from the child's
# ``issue_code.routing_model`` column (D12 section-pooled vs D18
# skill-matched). NEVER hardcode the model on the STALL path. ``'none'``
# (no-dispatch issue codes) has no dispatch routing — fall back to the
# skill-matched mechanism so ``routing.select`` still yields deterministically.
_ROUTING_MODEL_BY_CODE = {
    "section_pooled": routing.RoutingModel.SECTION_POOLED,  # D12
    "skill_matched": routing.RoutingModel.SKILL_MATCHED,    # D18
}

# §7.4 outcome vocabulary (ck_esc_state terminal dispositions reachable from
# ``open`` via apply_recommendation). ``hard_escalated`` is reached ONLY via
# ``hard_escalate`` (the D21 backstop), never as a direct outcome here.
_RESOLVE_OUTCOMES = ("approved", "edited", "overridden", "auto_proceeded")
# The single outcome whose post-state differs from ``approved`` ONLY by
# ``resolved_by_account_id is None`` (silence ≡ approve is STRUCTURAL).
_AUTO_PROCEEDED = "auto_proceeded"
_HARD_ESCALATED = "hard_escalated"
# Outcomes that execute the STORED recommendation verbatim; the rest carry a
# supervisor-supplied action (edited/overridden).
_STORED_REC_OUTCOMES = ("approved", _AUTO_PROCEEDED)

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
    "apply_reservation_mutation": lambda eid, p: RecApplyReservationMutation(
        recommendation_escalation_id=eid,
        field=p["field"], requested_value=p["requested_value"]),
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


async def _routing_model_for_child(s: AsyncSession,
                                   child: ChildSubRequest):
    """D1 FIX: derive the C1 routing model enum from the child's
    ``issue_code.routing_model`` column (engine-local read). Maps
    ``'section_pooled'``→D12, ``'skill_matched'``→D18; absent / ``'none'``
    falls back to skill-matched so ``routing.select`` stays deterministic.
    Routing is NOT re-implemented — only the model enum is selected."""
    if child.issue_code_id is not None:
        rm = (await s.execute(
            sa.select(IssueCode.routing_model)
            .where(IssueCode.id == child.issue_code_id)
        )).scalar_one_or_none()
        if rm in _ROUTING_MODEL_BY_CODE:
            return _ROUTING_MODEL_BY_CODE[rm]
    return routing.RoutingModel.SKILL_MATCHED


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
        # D1 FIX: the routing MODEL is DERIVED from the child's
        # issue_code.routing_model (D12 section-pooled vs D18 skill-matched),
        # NEVER hardcoded. The spine only selects the enum and calls C1.
        stalled = ctx.get("stalled_account_id")
        exclude = {stalled} if stalled is not None else set()
        model = await _routing_model_for_child(s, child)
        now = (await s.execute(sa.select(sa.func.now()))).scalar_one()
        sel = routing.select(
            model=model,
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

    # triage_flag — the flag verdict (D5/D24) + the D24 extracted target
    # (persisted at intake on the child; the LLM is never re-invoked here).
    return {"verdict": ctx.get("verdict"),
            "requested_checkout": getattr(child, "requested_checkout", None)}


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

    # §9.2/§7.4 D21: the D21 backstop is the slice's reason-to-exist —
    # repeated stall→auto-proceed(reassign)→stall cycles MUST, after N
    # cycles, hard-escalate. Each stall cycle is a DISTINCT Escalation
    # (an escalation resolves ONCE; D2/§7.4), so the running ``cycle_count``
    # accumulator has to be carried forward across the chain or every fresh
    # stall escalation restarts at 0 and auto-proceeds forever (the D21
    # bound would be UNREACHABLE in production for n_cycle_bound > 1).
    #
    # Seed the new escalation's ``cycle_count`` from the most-recent prior
    # ``stall`` Escalation for the SAME child (engine-local read, the
    # caller's session — the established shared/engine idiom; no commit).
    # The prior was already advanced by ``apply_recommendation``'s increment
    # when it auto-proceeded; the D21 gate (``cycle_count + 1 >=
    # n_cycle_bound``) in ``apply_recommendation`` then advances the chain
    # correctly. Scoped to ``trigger == "stall"`` ONLY — servicer_raised /
    # triage_flag are NOT the backstop cycle. No prior stall escalation
    # (first cycle / fresh child) → stays 0 (preserves D1).
    carried_cycle_count = 0
    if trig == EscalationTrigger.STALL.value:
        prior = (await s.execute(
            sa.select(Escalation.cycle_count)
            .where(Escalation.child_id == child.id,
                   Escalation.trigger == EscalationTrigger.STALL.value)
            .order_by(Escalation.created_at.desc())
            .limit(1)
        )).scalar_one_or_none()
        if prior is not None:
            carried_cycle_count = prior

    # --- Escalation(open) — C4 new-entity emission pattern (mirrors the
    # WorkOrder-creation hop in lifecycle._child_hops): instantiate, flush
    # for the id, emit EXACTLY ONE event via the writer. ``transition`` is
    # NOT used: the escalation machine has no ``*->open`` legal edge (``open``
    # is the server_default start state, not a transition). No second writer
    # path is invented.
    esc = Escalation(child_id=child.id, trigger=trig,
                     cycle_count=carried_cycle_count,
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


async def _child_for_escalation(s: AsyncSession,
                                esc: Escalation) -> ChildSubRequest:
    return (await s.execute(
        sa.select(ChildSubRequest)
        .where(ChildSubRequest.id == esc.child_id)
    )).scalar_one()


async def _active_ladder_for_escalation(s: AsyncSession, esc: Escalation,
                                        child: ChildSubRequest):
    """The property's active EscalationLadder (D21 — the bound lives here)."""
    property_id = await _property_id_for_child(s, child)
    if property_id is None:
        raise ConflictError(
            f"escalation {esc.id} child has no resolvable property")
    ladder = (await s.execute(
        sa.select(_EscalationLadder).where(
            _EscalationLadder.property_id == property_id,
            _EscalationLadder.status == "active")
    )).scalar_one_or_none()
    if ladder is None:
        raise ConflictError(
            f"no active EscalationLadder for property {property_id}")
    return ladder


async def _resolved_action(s: AsyncSession, esc: Escalation, outcome: str,
                           action, payload):
    """The typed (action, params) to execute.

    approved / auto_proceeded → the STORED Recommendation + its ``rec_*``
    detail, VERBATIM (silence ≡ approve is structural — same source).
    edited / overridden → the supervisor-SUPPLIED action + payload.
    """
    if outcome in _STORED_REC_OUTCOMES:
        rec = (await s.execute(
            sa.select(Recommendation)
            .where(Recommendation.escalation_id == esc.id)
        )).scalar_one()
        act = rec.action
        if act == "reassign":
            d = (await s.execute(sa.select(RecReassign).where(
                RecReassign.recommendation_escalation_id == esc.id)
            )).scalar_one()
            return act, {"target_account_id": d.target_account_id}
        if act == "broadcast":
            return act, {}
        if act == "relocate":
            d = (await s.execute(sa.select(RecRelocate).where(
                RecRelocate.recommendation_escalation_id == esc.id)
            )).scalar_one()
            return act, {"target_room_id": d.target_room_id}
        if act == "extend_sla":
            d = (await s.execute(sa.select(RecExtendSla).where(
                RecExtendSla.recommendation_escalation_id == esc.id)
            )).scalar_one()
            return act, {"extend_seconds": d.extend_seconds}
        if act == "apply_reservation_mutation":
            d = (await s.execute(sa.select(RecApplyReservationMutation).where(
                RecApplyReservationMutation.recommendation_escalation_id
                == esc.id))).scalar_one()
            return act, {"field": d.field,
                         "requested_value": d.requested_value}
        return act, {}  # approve / deny — no params
    # edited / overridden — the supervisor supplies the typed action.
    if action is None:
        raise ConflictError(
            f"outcome {outcome!r} requires a supervisor-supplied action")
    return action, dict(payload or {})


async def _execute_action(s: AsyncSession, esc: Escalation,
                          child: ChildSubRequest, act: str, params: dict,
                          actor_id, ctx: dict) -> None:
    """Effect the typed action — ONLY via the C4 orchestrator / timers /
    the real relocate_stay seam. Routing/recommendation/re-binding are NOT
    re-implemented here.

    reassign/broadcast → mutate the linked WorkOrder's assignee IN PLACE
    keeping the accountable owner UNCHANGED (D12/D18 — the owner stays
    accountable to Closed/SLA regardless of who later services). The C4
    machine has no ``*->reassign`` WorkOrder edge (assignee swap is not a
    state change); per the task this follows the C4 entity-mutation pattern
    (``transition`` mutates subject fields in place) — engine-local, the
    single escalation_resolved event still flows through C4 ``transition``.
    relocate → the escalation→relocate C4 hop (real ``relocate_stay`` +
    glitch close). extend_sla → re-arm a fresh timer. approve/deny → the
    mutation gate seam.
    """
    if act in ("reassign", "broadcast"):
        wo = (await s.execute(
            sa.select(WorkOrder).where(WorkOrder.child_id == child.id)
        )).scalar_one_or_none()
        if wo is None:
            return
        target = params.get("target_account_id")
        # reassign → in-place assignee swap to the routed target (the stored
        # Recommendation already captured C1 routing.select EXCLUDING the
        # stalled assignee at open time; edited/overridden carry the
        # supervisor target). broadcast → clear the direct assignment; the
        # accountable owner is UNCHANGED in BOTH cases.
        wo.assigned_servicer_id = target if act == "reassign" else None
        s.add(wo)
        return

    if act == "extend_sla":
        secs = params.get("extend_seconds")
        if secs is None:
            sla = await _sla_for_child(s, child)
            secs = (sla.fulfilment_sla_seconds if sla is not None
                    else DEFAULT_SUPERVISOR_SLA_SECONDS)
        now = (await s.execute(sa.select(sa.func.now()))).scalar_one()
        from conduit.shared.engine.timers import TimerType, arm
        await arm(s, "escalation_id", esc.id, TimerType.SUPERVISOR_SLA,
                  fire_at=now + dt.timedelta(seconds=int(secs)))
        return

    # relocate is effected by the C4 escalation→relocate hop (real
    # relocate_stay + glitch close) driven by the single escalation
    # transition below — NOTHING to do here.
    # approve / deny — the reservation-mutation gate. No built mutation-gate
    # surface exists in this slice; the C4 escalation transition records the
    # disposition (one event). Spec-faithful seam — see REPORT.
    return


async def apply_recommendation(s: AsyncSession, escalation: Escalation, *,
                               outcome: str, action=None, payload=None,
                               actor=None, **ctx) -> Escalation:
    """THE single executor (Spec §7.4).

    ``outcome ∈ {approved, edited, overridden, auto_proceeded}``. BOTH the
    human path (supervisor/services/decisions.resolve) and the timer
    auto-proceed (engine/runner) call this — silence ≡ approve is STRUCTURAL:
    the auto_proceeded post-state is IDENTICAL to approved EXCEPT
    ``resolved_by_account_id is None``. No behaviour branches on the outcome
    otherwise.

    Executes the typed action via the C4 orchestrator / timers / the real
    relocate_stay seam, transitions the Escalation to the outcome state
    through C4 ``lifecycle.transition`` (exactly ONE ``escalation_resolved``
    event), sets the resolver + ``resolved_at``, and increments
    ``cycle_count``. D21: if ``cycle_count + 1 >= active ladder.n_cycle_bound``
    on the silent auto-proceed path → ``hard_escalate`` INSTEAD (auto-proceed
    disabled at/after the floor). One transaction, the caller's session, NO
    commit.
    """
    if outcome not in _RESOLVE_OUTCOMES:
        raise ConflictError(f"unknown apply_recommendation outcome {outcome!r}")

    actor_id = getattr(actor, "id", actor)

    child = await _child_for_escalation(s, escalation)
    ladder = await _active_ladder_for_escalation(s, escalation, child)

    # D21 bound — auto-proceed (the silent path) is DISABLED at/after the
    # floor: if this cycle would reach the bound, hard-escalate INSTEAD of
    # executing the action. Human decisions (approved/edited/overridden) are
    # explicit and proceed; only the silence path is bounded (D21).
    if (outcome == _AUTO_PROCEEDED
            and escalation.cycle_count + 1 >= ladder.n_cycle_bound):
        return await hard_escalate(s, escalation)

    act, params = await _resolved_action(
        s, escalation, outcome, action, payload)

    # Effect the typed action FIRST (reassign/broadcast/extend_sla); relocate
    # is effected by the single C4 escalation transition's hop below.
    await _execute_action(s, escalation, child, act, params, actor_id, ctx)

    resolver = None if outcome == _AUTO_PROCEEDED else actor_id

    # The ONE escalation_resolved event + (for relocate) the C4
    # escalation→relocate hop, through the single writer path. Pass the
    # resolved action + relocate ctx so C4's hop runs the real relocate_stay.
    await lifecycle.transition(
        s, escalation, outcome, actor_account_id=resolver,
        action=act, **ctx)

    escalation.resolved_by_account_id = resolver
    escalation.resolved_at = (
        await s.execute(sa.select(sa.func.now()))).scalar_one()
    escalation.cycle_count = escalation.cycle_count + 1
    s.add(escalation)
    return escalation


async def hard_escalate(s: AsyncSession, escalation: Escalation) -> Escalation:
    """D21 backstop: surface to the non-time-boxed duty manager.

    Transitions the Escalation → ``hard_escalated`` via C4
    ``lifecycle.transition`` (exactly ONE ``escalation_resolved`` event), with
    NO recommendation action executed and NO out-of-band side effect
    (in-portal only). Auto-proceed is disabled past this point (the state is
    terminal in the escalation machine). One transaction, caller's session,
    NO commit.
    """
    await lifecycle.transition(s, escalation, _HARD_ESCALATED,
                               actor_account_id=None)
    escalation.resolved_by_account_id = None
    escalation.resolved_at = (
        await s.execute(sa.select(sa.func.now()))).scalar_one()
    s.add(escalation)
    return escalation
