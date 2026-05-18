"""Intake orchestration — the guest-side use-case that drives triage.

Triage is not a portal slice (no triage/ api·services·dal·schemas). The
*mechanism* is shared domain (conduit.shared.domain.triage); this service is
just where it is triggered: decompose → per-child classify+triage → echo split
if >1 (D36) → route AUTO / clarify / flag / no-dispatch.

Orchestration only: mechanism lives in shared.domain (triage, grounding,
lifecycle); events go through lifecycle.transition / the shared writer; the
DAL is add-only; this service flushes; the API handler commits (Task 12).
"""
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from conduit.core.exceptions import ConflictError, NotFoundError
from conduit.guest.dal import bindings
from conduit.guest.dal import children as cdal
from conduit.guest.dal import requests as rdal
from conduit.guest.dal import resolutions as resdal
from conduit.guest.services import nodispatch
from conduit.guest.services import smalltalk
from conduit.core.config import get_settings
from conduit.shared.domain import conversation, lifecycle, routing, triage
from conduit.shared.engine import spine
from conduit.shared.events import writer
from conduit.shared.integrations.openai import LLMUnavailable
from conduit.shared.models import (IssueCode, Request, Room, Roster,
                                   RosterAssignment, Section, SLAPreset,
                                   StaffProfile, StaffSkill, Stay)
from conduit.supervisor.dal import issue_codes as icdal

# D12 section-pooled vs D18 skill-matched — derived from the child's
# ``issue_code.routing_model`` column, NEVER hardcoded (mirrors the spine's
# ``_ROUTING_MODEL_BY_CODE``; routing RULES stay in C1 ``routing.select``).
_ROUTING_MODEL_BY_CODE = {
    "section_pooled": routing.RoutingModel.SECTION_POOLED,  # D12
    "skill_matched": routing.RoutingModel.SKILL_MATCHED,    # D18
}


async def _route_dispatch_child(s: AsyncSession, child, ic, actor_id) -> dict:
    """Triage AUTO + ``fulfilment_mode == 'dispatch'`` ⇒ the C4 routing-effect
    (Spec §9.2). The routing MODEL is derived from
    ``issue_code.routing_model``; candidates are an engine-local read off the
    caller's session (the established ``shared/engine/spine`` idiom — services
    may read); C1 ``routing.select`` OWNS the allocation rule; the resolved
    pure ``Selection`` is passed into C4 ``lifecycle.transition(child,
    'routing', ...)`` which creates the WorkOrder + arms accept_window +
    fulfilment_sla (NOT reimplemented here). Then the WorkOrder + child are
    advanced to ``pushed`` / ``broadcast`` through the SAME C4 writer path."""
    # child → Request → Stay → Room → Section (the owning section + property).
    sec_row = (await s.execute(
        sa.select(Section.id, Section.property_id)
        .select_from(Request)
        .join(Stay, Stay.id == Request.stay_id)
        .join(Room, Room.id == Stay.room_id)
        .join(Section, Section.id == Room.section_id)
        .where(Request.id == child.request_id)
    )).first()
    section_id = sec_row[0] if sec_row else None
    property_id = sec_row[1] if sec_row else None

    model = _ROUTING_MODEL_BY_CODE.get(
        ic.routing_model, routing.RoutingModel.SKILL_MATCHED)

    # priority_tier via issue_code.sla_preset_id → SLAPreset.tier (D23).
    priority_tier = "P3"
    if ic.sla_preset_id is not None:
        tier = (await s.execute(
            sa.select(SLAPreset.tier).where(SLAPreset.id == ic.sla_preset_id)
        )).scalar_one_or_none()
        if tier:
            priority_tier = tier

    # Engine-local candidate read (same shape spine._stall_candidates builds,
    # enriched with section-ownership / in-zone / skills so the PURE C1
    # select can decide D12/D18). Routing rules are NOT re-implemented.
    rosters = {
        r.id: r for r in (await s.execute(
            sa.select(Roster).where(Roster.property_id == property_id)
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

    # C4 owns WorkOrder creation + timer arming — pass the pure Selection in.
    await lifecycle.transition(
        s, child, "routing", actor_account_id=actor_id,
        selection=sel, kind="dispatch", routing_model=ic.routing_model,
        priority_tier=priority_tier)
    await s.flush()

    # Advance the freshly-created WorkOrder to pushed / broadcast through the
    # SAME C4 writer path (assigned ⇒ pushed to the owner; else claim-fallback
    # broadcast — D12/D18). The dispatch leg's state lives on the WorkOrder;
    # the child stays at ``routing`` (C4 models no child pushed/broadcast
    # event — the WorkOrder carries that hop).
    from conduit.shared.models import WorkOrder
    wo = (await s.execute(
        sa.select(WorkOrder).where(WorkOrder.child_id == child.id)
    )).scalar_one()
    nxt = "pushed" if sel.assigned_id is not None else "broadcast"
    await lifecycle.transition(s, wo, nxt, actor_account_id=actor_id)
    return {"terminal": "dispatched", "state": wo.state}


async def submit_request(s: AsyncSession, actor, text: str) -> dict:
    trio = await bindings.get_active_binding_for_guest(s, actor.id)
    if trio is None:
        raise ConflictError("no active stay to action")
    stay, room, section = trio
    ambient = {"room_label": room.label, "section_label": section.label,
               "check_in": stay.check_in, "check_out": stay.check_out,
               "stay_status": stay.status}
    req = await rdal.insert_request(s, guest_account_id=actor.id,
        stay_id=stay.id, raw_text=text)
    await s.flush()
    await writer.emit_request_created(s, req.id, actor.id)
    catalog = [dict(code=c.code, label=c.label,
                    fulfilment_mode=c.fulfilment_mode,
                    is_reservation_mutation=c.is_reservation_mutation)
               for c in await icdal.list_codes(s, status="active")]
    # --- Conversation window (extraction-only, Spec §7.1) ----------------
    # Reuse the EXACT read model the conversation view uses: prior requests
    # for this guest on the ACTIVE stay (request.stay_id == stay.id),
    # interleaved guest raw_text + system grounded answer_text, time-ordered
    # (rdal.list_requests_for_guest orders by created_at ascending — the
    # window module assumes caller-ordered oldest→newest).
    turns: list[conversation.Turn] = []
    prior = await rdal.list_requests_for_guest(s, actor.id)
    for pr in prior:
        if pr.id == req.id:
            continue                                   # the in-flight msg
        if pr.stay_id != stay.id:
            continue                                   # per-stay isolation
        turns.append(conversation.Turn(role="guest", text=pr.raw_text))
        for c in await cdal.list_children_for_request(s, pr.id):
            res = await resdal.get_resolution(s, c.id)
            if res is not None and res.answer_text:
                turns.append(conversation.Turn(
                    role="system", text=res.answer_text))
    history = conversation.window(
        turns, limit=get_settings().conversation_window)
    # D35/D5 reorder (Spec §7.3, additive): decompose the raw message into
    # independent need-texts, then run the EXISTING per-child classify +
    # insert + routing chain UNCHANGED for each one. Single-need stays
    # byte-identical (fake_decompose / real decompose → [raw_text]). Siblings
    # share only the parent ``req`` — independent fates per loop iteration.
    children_out = []
    for child_text in await triage.decompose(text):
        try:
            triaged = await triage.classify(child_text, catalog, history)
        except LLMUnavailable:                         # AD11 degrade only
            triaged = [triage.TriagedChild(text=child_text, issue_code=None,
                outcome=triage.TriageOutcome("clarify"), uncategorized=True,
                is_problem_report=False)]
        for t in triaged:
            ic = None
            if t.issue_code:
                ic = await icdal.get_by_code(s, t.issue_code)
            child = await cdal.insert_child(s, request_id=req.id, text=t.text,
                issue_code_id=ic.id if ic else None,
                uncategorized=t.uncategorized,
                outcome=t.outcome.value,
                fulfilment_mode=(ic.fulfilment_mode if ic else None),
                is_problem_report=t.is_problem_report,
                requested_checkout=t.requested_checkout, state="intake")
            await s.flush()
            await lifecycle.transition(s, child, "triaged",
                actor_account_id=actor.id)
            if ic is not None and ic.code == "SMALLTALK":
                term = await smalltalk.resolve(s, child, actor.id)
            elif t.outcome.value == "no_dispatch":
                term = await nodispatch.resolve(s, child, ambient, actor.id,
                                                history=history)
            elif (t.outcome.value == "auto" and ic is not None
                  and ic.fulfilment_mode == "dispatch"):
                # AUTO + dispatch ⇒ branch to the C4 routing-effect (§9.2).
                # All other outcomes (clarify/flag/uncategorized/no-code
                # AUTO) keep the byte-identical park behaviour below —
                # back-compat.
                term = await _route_dispatch_child(s, child, ic, actor.id)
            elif (t.outcome.value == "flag" and ic is not None
                  and ic.is_reservation_mutation):
                # D24 answer↔action seam: ONLY a reservation-mutation flag
                # rides the spine's generic FLAG trigger → decision queue
                # (Spec §7.3). Every other terminal case keeps the
                # byte-identical park below (minimal blast radius).
                # open_escalation reads child.requested_checkout via
                # _assemble_context (Task 11d) — the child row was flushed
                # above (insert + lifecycle transition).
                await spine.open_escalation(
                    s, child, "triage_flag",
                    actor_account_id=actor.id, verdict="approve")
                term = {"terminal": "flagged", "state": child.state}
            else:
                await writer.emit_child(s, "child_parked", child.id,
                                        actor.id)
                term = {"terminal": "logged"}
            children_out.append({"child_id": str(child.id), "text": t.text,
                "issue_code": t.issue_code,
                "issue_label": (ic.label if ic is not None else None),
                "outcome": t.outcome.value, **term})
    split = len(children_out) >= 2
    return {"request_id": str(req.id), "split": split,
            "children": children_out}


async def confirm(s: AsyncSession, actor, child_id, helpful: bool) -> dict:
    child = await cdal.get_child(s, child_id)
    if child is None:
        raise NotFoundError("child not found")
    req = await rdal.get_request(s, child.request_id)
    if req is None or str(req.guest_account_id) != str(actor.id):
        raise NotFoundError("child not found")          # ownership (no leak)
    if child.state != "answered":
        raise ConflictError("not awaiting confirmation")
    res = await resdal.get_resolution(s, child.id)
    await resdal.set_helpful(s, res, "yes" if helpful else "no")
    if helpful:
        await lifecycle.transition(s, child, "closed",
            actor_account_id=actor.id)
        return {"child_id": str(child.id), "text": child.text,
                "terminal": "answered", "closure_prompt": False,
                "state": "closed"}
    await lifecycle.transition(s, child, "reopened",
        actor_account_id=actor.id)
    await lifecycle.transition(s, child, "concierge_queue",
        actor_account_id=actor.id)
    return {"child_id": str(child.id), "text": child.text,
            "terminal": "logged", "closure_prompt": False,
            "state": "concierge_queue"}
