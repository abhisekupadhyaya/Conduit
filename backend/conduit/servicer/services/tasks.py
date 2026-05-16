"""Servicer task actions — claim / accept / start / complete / raise.

Orchestration only (Spec §8 / §9.2). Ownership + zone + state guards raise
the merged ``core/exceptions`` (foreign WO → ``NotFoundError`` → 404;
not-in-zone → ``ForbiddenError`` → 403; not-claimable / illegal state →
``ConflictError`` → 409). All EFFECTING goes through the C4
``lifecycle.transition`` writer path and the spine ``open_escalation`` ONLY
— NO parallel writer, NO reimplemented routing/availability/spine.

``claim`` is an assignee mutation, NOT a WorkOrder state change (D12: the
WorkOrder machine has no ``broadcast->claim`` edge — being claimed does not
move the state). It therefore follows the C4/D2-established entity-mutation
pattern used by the spine's ``_execute_action`` reassign/broadcast hop:
mutate ``assigned_servicer_id`` IN PLACE through the ORM, leaving
``accountable_owner_id`` UNCHANGED (D12 — the committed owner stays
accountable to Closed/SLA regardless of who later services it). No raw
bypass of the writer is introduced: claim has no lifecycle event by design.

The DAL is add-only / no-flush / no-commit; this service flushes; the API
commits at the edge. Reads never commit.
"""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from conduit.core.deps import Actor
from conduit.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from conduit.servicer.dal import tasks as tdal
from conduit.shared.domain import lifecycle
from conduit.shared.engine import spine
from conduit.shared.models import ChildSubRequest


async def list_tasks(s: AsyncSession, actor: Actor) -> list[dict]:
    """Polled, self-scoped pushed + claimable queue. A read — never commits."""
    return await tdal.list_tasks(s, uuid.UUID(str(actor.id)))


async def _owned(s: AsyncSession, actor: Actor,
                 wo_id: uuid.UUID):
    """Resolve the WorkOrder ONLY within the caller's scope (no leak).

    A non-existent OR foreign WO is INDISTINGUISHABLE from the caller's
    point of view → ``NotFoundError`` (404) in BOTH cases (no enumeration
    oracle)."""
    wo = await tdal.get_owned_work_order(
        s, wo_id, uuid.UUID(str(actor.id)))
    if wo is None:
        raise NotFoundError("task not found")
    return wo


async def claim(s: AsyncSession, actor: Actor,
                wo_id: uuid.UUID) -> dict:
    """Claim a broadcast task (D12). Not found → 404; not a broadcast task
    → 409; not in the caller's claim zone → 403. On success the caller
    becomes ``assigned_servicer_id``; ``accountable_owner_id`` is UNCHANGED
    (D12 — asserted by the API test)."""
    account_id = uuid.UUID(str(actor.id))
    wo = await tdal.get_work_order(s, wo_id)
    if wo is None:
        raise NotFoundError("task not found")
    if wo.state != "broadcast":
        raise ConflictError("task is not claimable")
    sections = await tdal.caller_claim_sections(s, account_id)
    if wo.section_id is None or wo.section_id not in sections:
        raise ForbiddenError("task is not in your zone")

    # C4/D2 entity-mutation pattern (mirrors spine ``_execute_action``):
    # in-place assignee swap through the ORM. ``accountable_owner_id`` is
    # deliberately NOT touched (D12). No state change ⇒ no lifecycle event
    # (the WorkOrder machine has no ``broadcast->claim`` edge — claim is not
    # a transition); no parallel writer is invented.
    wo.assigned_servicer_id = account_id
    s.add(wo)
    await s.flush()
    return {"work_order_id": str(wo.id), "state": wo.state,
            "assigned_servicer_id": str(wo.assigned_servicer_id)}


async def _transition(s: AsyncSession, actor: Actor, wo_id: uuid.UUID,
                      to: str) -> dict:
    """Guarded WorkOrder transition via the C4 writer ONLY. Foreign → 404;
    illegal ``state->to`` → ``ConflictError`` (409, raised by the
    orchestrator's legality guard — side-effect-free)."""
    wo = await _owned(s, actor, wo_id)
    await lifecycle.transition(s, wo, to, actor_account_id=actor.id)
    return {"work_order_id": str(wo.id), "state": wo.state}


async def accept(s: AsyncSession, actor: Actor,
                 wo_id: uuid.UUID) -> dict:
    """Accept — the C4 hop cancels the accept_window timer (D23)."""
    return await _transition(s, actor, wo_id, "accepted")


async def start(s: AsyncSession, actor: Actor,
                wo_id: uuid.UUID) -> dict:
    """Begin work → ``in_progress``."""
    return await _transition(s, actor, wo_id, "in_progress")


async def complete(s: AsyncSession, actor: Actor, wo_id: uuid.UUID,
                   notes: str | None) -> dict:
    """Complete (carries optional ``notes``). The C4 WO→completed hop drives
    the linked child → ``done_pending_confirm``. Notes are stamped on the
    WorkOrder BEFORE the transition so they persist in the SAME transaction
    as the single ``work_order_completed`` event."""
    wo = await _owned(s, actor, wo_id)
    if notes is not None:
        wo.completion_notes = notes
        s.add(wo)
    await lifecycle.transition(s, wo, "completed",
                               actor_account_id=actor.id)
    return {"work_order_id": str(wo.id), "state": wo.state}


async def raise_escalation(s: AsyncSession, actor: Actor, wo_id: uuid.UUID,
                           reason: str) -> dict:
    """D20 servicer-raised mid-lifecycle escalation. Foreign → 404. Reuses
    the spine ``open_escalation`` (trigger ``servicer_raised``) — the
    escalation + its AI recommendation + the supervisor_sla timer are ALL
    produced by the spine; nothing is re-implemented here."""
    wo = await _owned(s, actor, wo_id)
    child = (await s.execute(
        select(ChildSubRequest).where(ChildSubRequest.id == wo.child_id)
    )).scalar_one()
    esc = await spine.open_escalation(
        s, child, spine.EscalationTrigger.SERVICER_RAISED,
        actor_account_id=actor.id, reason=reason)
    return {"escalation_id": str(esc.id), "state": esc.state,
            "trigger": esc.trigger}
