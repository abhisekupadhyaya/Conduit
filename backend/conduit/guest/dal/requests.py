# conduit/guest/dal/requests.py
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from conduit.shared.models import (
    Account,
    ChildSubRequest,
    Glitch,
    IssueCode,
    Request,
    Stay,
    WorkOrder,
)


async def insert_request(s: AsyncSession, *, guest_account_id, stay_id,
                          raw_text, channel="text") -> Request:
    obj = Request(guest_account_id=guest_account_id, stay_id=stay_id,
                  raw_text=raw_text, channel=channel)
    s.add(obj)
    return obj


async def get_request(s: AsyncSession, id: uuid.UUID) -> Request | None:
    return await s.get(Request, id)


async def list_requests_for_guest(s: AsyncSession, guest_account_id: uuid.UUID):
    res = await s.execute(select(Request)
        .where(Request.guest_account_id == guest_account_id)
        .order_by(Request.created_at))
    return res.scalars().all()


async def list_dispatch_cards_for_active_stay(
    s: AsyncSession, guest_account_id: uuid.UUID
) -> list[dict]:
    """Self-scoped dispatch status cards (Spec §8 / §9.2). Read-only.

    Joins child → its WorkOrder's assigned servicer display NAME (D17) +
    ``revised_eta`` + an open-Glitch badge, filtered to the CALLER's ACTIVE
    stay ONLY (child→Request→Stay, ``Stay.status == 'active'`` AND
    ``Request.guest_account_id == caller``). The double scope means no
    cross-stay / cross-guest leakage — a security-adjacent must. Add-only,
    no flush, no commit.
    """
    srv = aliased(Account)
    rows = (await s.execute(
        select(
            ChildSubRequest.id,
            ChildSubRequest.state,
            WorkOrder.state,
            ChildSubRequest.revised_eta,
            IssueCode.label,
            srv.display_name,
            Glitch.id,
        )
        .select_from(ChildSubRequest)
        .join(Request, Request.id == ChildSubRequest.request_id)
        .join(Stay, Stay.id == Request.stay_id)
        .outerjoin(IssueCode, IssueCode.id == ChildSubRequest.issue_code_id)
        .outerjoin(WorkOrder, WorkOrder.child_id == ChildSubRequest.id)
        .outerjoin(srv, srv.id == WorkOrder.assigned_servicer_id)
        .outerjoin(
            Glitch,
            (Glitch.child_id == ChildSubRequest.id)
            & (Glitch.state.in_(("open", "held_open"))),
        )
        .where(
            Request.guest_account_id == guest_account_id,
            Stay.status == "active",
            ChildSubRequest.fulfilment_mode == "dispatch",
        )
        .order_by(ChildSubRequest.created_at)
    )).all()
    # The dispatch leg's progress lives on the WorkOrder (pushed/broadcast/
    # accepted/in_progress/...); the child sits at ``routing`` until it goes
    # done_pending_confirm/closed/reopened/cancelled. The guest-facing card
    # ``state`` therefore surfaces the WorkOrder state while one is active,
    # falling back to the child state once the child itself advances
    # (done_pending_confirm → closed/reopened/cancelled).
    cards = []
    for (cid, c_state, wo_state, revised_eta, label, srv_name, gid) in rows:
        state = wo_state if (wo_state is not None
                             and c_state == "routing") else c_state
        cards.append({
            "child_id": str(cid),
            "state": state,
            "issue_label": label,
            "assigned_servicer_name": srv_name,
            "revised_eta": revised_eta,
            "glitch": gid is not None,
        })
    return cards


async def get_dispatch_child_for_guest(
    s: AsyncSession, child_id: uuid.UUID, guest_account_id: uuid.UUID
) -> ChildSubRequest | None:
    """Fetch a child ONLY if it belongs to the caller's stay (no leak).

    Returns ``None`` when the child does not exist OR is not the caller's —
    the service maps that to ``NotFoundError`` (foreign child → 404). Scoped
    via child→Request→Stay with ``Request.guest_account_id == caller``."""
    return (await s.execute(
        select(ChildSubRequest)
        .join(Request, Request.id == ChildSubRequest.request_id)
        .where(ChildSubRequest.id == child_id,
               Request.guest_account_id == guest_account_id)
    )).scalar_one_or_none()
