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

from sqlalchemy.ext.asyncio import AsyncSession

from conduit.core.exceptions import ConflictError, NotFoundError
from conduit.guest.dal import bindings
from conduit.guest.dal import children as cdal
from conduit.guest.dal import requests as rdal
from conduit.guest.dal import resolutions as resdal
from conduit.guest.services import nodispatch
from conduit.shared.domain import lifecycle, triage
from conduit.shared.events import writer
from conduit.shared.integrations.openai import LLMUnavailable
from conduit.supervisor.dal import issue_codes as icdal


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
    try:
        triaged = await triage.classify(text, catalog)
    except LLMUnavailable:                             # AD11 degrade only
        triaged = [triage.TriagedChild(text=text, issue_code=None,
            outcome=triage.TriageOutcome("clarify"), uncategorized=True,
            is_problem_report=False)]
    children_out = []
    for t in triaged:
        ic = None
        if t.issue_code:
            ic = await icdal.get_by_code(s, t.issue_code)
        child = await cdal.insert_child(s, request_id=req.id, text=t.text,
            issue_code_id=ic.id if ic else None, uncategorized=t.uncategorized,
            outcome=t.outcome.value,
            fulfilment_mode=(ic.fulfilment_mode if ic else None),
            is_problem_report=t.is_problem_report, state="intake")
        await s.flush()
        await lifecycle.transition(s, child, "triaged",
            actor_account_id=actor.id)
        if t.outcome.value == "no_dispatch":
            term = await nodispatch.resolve(s, child, ambient, actor.id)
        else:
            await writer.emit_child(s, "child_parked", child.id, actor.id)
            term = {"terminal": "logged"}
        children_out.append({"child_id": str(child.id), "text": t.text,
            "issue_code": t.issue_code, **term})
    return {"request_id": str(req.id), "children": children_out}


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
        return {"child_id": str(child.id), "terminal": "answered",
                "state": "closed"}
    await lifecycle.transition(s, child, "reopened",
        actor_account_id=actor.id)
    await lifecycle.transition(s, child, "concierge_queue",
        actor_account_id=actor.id)
    return {"child_id": str(child.id), "terminal": "logged",
            "state": "concierge_queue"}
