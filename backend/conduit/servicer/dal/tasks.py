# conduit/servicer/dal/tasks.py
"""Self-scoped servicer task reads (Spec §8 / §9.2). Read-only:
add-only / no-flush / no-commit (the merged DAL discipline).

Resolution E (spec §4 "Portal ownership"): the servicer owns its own task
reads through THIS module; it must NOT import ``supervisor/dal``. Every
query is filtered by the authenticated ``account_id`` — there is NO
cross-servicer leak (a security-adjacent must):

* PUSHED (owned, D12/D18): WorkOrders whose ``accountable_owner_id`` OR
  ``assigned_servicer_id`` IS the caller, in a non-terminal state.
* CLAIMABLE (claim-fallback, D12): ``broadcast`` WorkOrders whose
  ``section_id`` is one the caller currently has an ACTIVE
  ``RosterAssignment`` for AND the caller is ``effective_available`` now
  (the pure ``shared.domain.availability`` predicate — CALLED, never
  re-derived). Off-shift / on-break ⇒ nothing claimable.

Live deadlines (D23) come from the related accept_window / fulfilment_sla
``Timer`` rows (armed against the child by the C4 ``_child_hops``);
self-scoped reads never widen past the caller's rows.
"""
from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from conduit.core import clock
from conduit.servicer.dal import self as self_dal
from conduit.shared.domain import availability
from conduit.shared.models import IssueCode, Timer, WorkOrder

# A WorkOrder is "live" (still actionable / shown) while it is on the
# pre-terminal arc — completed/cancelled drop off the working queue.
_LIVE_WO_STATES = ("created", "pushed", "broadcast", "accepted",
                   "in_progress")


async def _deadlines(s: AsyncSession,
                     child_ids: list[uuid.UUID]) -> dict:
    """child_id → {accept_window, fulfilment_sla} pending fire_at (D23)."""
    out: dict = {}
    if not child_ids:
        return out
    rows = (await s.execute(
        select(Timer.child_id, Timer.type, Timer.fire_at).where(
            Timer.child_id.in_(child_ids),
            Timer.state == "pending",
            Timer.type.in_(("accept_window", "fulfilment_sla")),
        )
    )).all()
    for cid, ttype, fire_at in rows:
        out.setdefault(cid, {})[ttype] = fire_at
    return out


async def _claimable_section_ids(s: AsyncSession,
                                 account_id: uuid.UUID) -> set[uuid.UUID]:
    """The sections the caller may claim in RIGHT NOW: only if the caller is
    ``effective_available`` (pure predicate — CALLED, not re-derived) AND the
    section comes from an ACTIVE roster assignment whose roster window covers
    business ``now``."""
    profile = await self_dal.get_profile(s, account_id)
    assignments = await self_dal.get_assignments(s, account_id)
    now = clock.now()
    if profile is None or not availability.effective_available(
        profile, assignments, now
    ):
        return set()
    w = availability.current_window(assignments, now)
    if w is None:
        return set()
    return {
        a.section_id
        for a in assignments
        if a.status == "active"
        and a.section_id is not None
        and a.roster is not None
        and a.roster.id == w.id
    }


def _card(wo: WorkOrder, kind: str, label: str | None,
          dl: dict) -> dict:
    return {
        "work_order_id": str(wo.id),
        "child_id": str(wo.child_id),
        "kind": kind,
        "state": wo.state,
        "priority_tier": wo.priority_tier,
        "issue_label": label,
        "accept_window_deadline": dl.get("accept_window"),
        "fulfilment_sla_deadline": dl.get("fulfilment_sla"),
    }


async def list_tasks(s: AsyncSession,
                     account_id: uuid.UUID) -> list[dict]:
    """Self-scoped pushed (owned) + claimable (in-zone broadcast) tasks with
    live SLA / accept-window deadlines (Spec §8). Read-only — no flush, no
    commit. NO cross-servicer leak: pushed is owner/assignee == caller;
    claimable is gated by the caller's own availability + zone."""
    # PUSHED — owner or assignee is the caller, non-terminal.
    pushed = (await s.execute(
        select(WorkOrder).where(
            ((WorkOrder.accountable_owner_id == account_id)
             | (WorkOrder.assigned_servicer_id == account_id)),
            WorkOrder.state.in_(_LIVE_WO_STATES),
        ).order_by(WorkOrder.created_at)
    )).scalars().all()

    # CLAIMABLE — broadcast WOs in the caller's currently-claimable sections,
    # excluding any already surfaced as pushed (owner == caller).
    section_ids = await _claimable_section_ids(s, account_id)
    pushed_ids = {wo.id for wo in pushed}
    claimable: list[WorkOrder] = []
    if section_ids:
        claimable = [
            wo for wo in (await s.execute(
                select(WorkOrder).where(
                    WorkOrder.state == "broadcast",
                    WorkOrder.section_id.in_(section_ids),
                ).order_by(WorkOrder.created_at)
            )).scalars().all()
            if wo.id not in pushed_ids
        ]

    all_wos = list(pushed) + claimable
    child_ids = [wo.child_id for wo in all_wos]
    # issue labels via the child's issue code (one round-trip)
    from conduit.shared.models import ChildSubRequest
    label_by_child: dict = {}
    if child_ids:
        for cid, label in (await s.execute(
            select(ChildSubRequest.id, IssueCode.label)
            .select_from(ChildSubRequest)
            .outerjoin(IssueCode,
                       IssueCode.id == ChildSubRequest.issue_code_id)
            .where(ChildSubRequest.id.in_(child_ids))
        )).all():
            label_by_child[cid] = label
    dl = await _deadlines(s, child_ids)

    cards = [
        _card(wo, "pushed", label_by_child.get(wo.child_id),
              dl.get(wo.child_id, {}))
        for wo in pushed
    ] + [
        _card(wo, "claimable", label_by_child.get(wo.child_id),
              dl.get(wo.child_id, {}))
        for wo in claimable
    ]
    return cards


async def get_owned_work_order(
    s: AsyncSession, wo_id: uuid.UUID, account_id: uuid.UUID
) -> WorkOrder | None:
    """A WorkOrder ONLY if the caller owns/services it (no cross-servicer
    leak). A non-existent OR foreign WO is INDISTINGUISHABLE from the
    caller's point of view → the service maps both to ``NotFoundError``
    (404, no enumeration oracle)."""
    return (await s.execute(
        select(WorkOrder).where(
            WorkOrder.id == wo_id,
            ((WorkOrder.accountable_owner_id == account_id)
             | (WorkOrder.assigned_servicer_id == account_id)),
        )
    )).scalar_one_or_none()


async def get_work_order(
    s: AsyncSession, wo_id: uuid.UUID
) -> WorkOrder | None:
    """Unscoped fetch — used ONLY by ``claim`` (a broadcast WO has no
    assignee yet, so it can't be owner-scoped). The service still enforces
    the zone gate before any effect, so this is not a leak path: ``claim``
    never returns WO contents, only a status."""
    return await s.get(WorkOrder, wo_id)


async def caller_claim_sections(
    s: AsyncSession, account_id: uuid.UUID
) -> set[uuid.UUID]:
    """Public accessor for the claim zone gate (the service decides 403)."""
    return await _claimable_section_ids(s, account_id)
