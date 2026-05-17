"""Guest dispatch surface (Spec §8 / §9.2): status cards + the three guarded
guest actions. Ambient identity/stay (D3a) — NO ids in request bodies.

Per-handler ``require_roles("guest")`` (server-side). Mutating handlers commit
at the edge; the read NEVER commits. Domain errors raised by the service
(merged ``core/exceptions``) are mapped to 404/409/422 by the merged
``install_exception_handlers``. Guarded transitions are dedicated ACTION
endpoints — there is deliberately NO ``DELETE`` handler, so DELETE → 405.
"""
from __future__ import annotations

import uuid as _u

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from conduit.core.deps import Actor, db_session, require_roles
from conduit.guest.dal import requests as rdal
from conduit.guest.schemas.requests import ChildStateOut, DispatchCardOut
from conduit.guest.services import conversation

router = APIRouter(tags=["guest-dispatch"])
_guest = require_roles("guest")


@router.get("/requests", response_model=list[DispatchCardOut])
async def list_requests(actor: Actor = Depends(_guest),
                        s: AsyncSession = Depends(db_session)):
    """Polled status cards, self-scoped to the caller's ACTIVE stay (D17).
    A read — it never commits."""
    return await rdal.list_dispatch_cards_for_active_stay(s, actor.id)


@router.post("/requests/{child_id}/confirm", response_model=ChildStateOut)
async def confirm(child_id: str, actor: Actor = Depends(_guest),
                  s: AsyncSession = Depends(db_session)):
    """Guest confirms the dispatched work → child Closed (D8)."""
    out = await conversation.confirm(s, actor, _u.UUID(child_id))
    await s.commit()
    return out


@router.post("/requests/{child_id}/reopen", response_model=ChildStateOut)
async def reopen(child_id: str, actor: Actor = Depends(_guest),
                 s: AsyncSession = Depends(db_session)):
    """Guest says it is NOT resolved → child Reopened."""
    out = await conversation.reopen(s, actor, _u.UUID(child_id))
    await s.commit()
    return out


@router.post("/requests/{child_id}/cancel", response_model=ChildStateOut)
async def cancel(child_id: str, actor: Actor = Depends(_guest),
                 s: AsyncSession = Depends(db_session)):
    """Guest cancels — allowed until Closed; the committed servicer is
    notified via the C4 ``child_cancelled`` event (D37)."""
    out = await conversation.cancel(s, actor, _u.UUID(child_id))
    await s.commit()
    return out
