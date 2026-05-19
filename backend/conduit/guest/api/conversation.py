"""The conversation IS the guest portal: ask + status + confirm."""
from __future__ import annotations

import uuid as _u

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from conduit.core.deps import Actor, db_session, require_roles
from conduit.guest.dal import children as cdal
from conduit.guest.dal import requests as rdal
from conduit.guest.dal import resolutions as resdal
from conduit.guest.schemas.conversation import (
    AskIn,
    ChildOut,
    ConfirmIn,
    RequestOut,
)
from conduit.guest.services import intake

router = APIRouter(tags=["guest-conversation"])
_guest = require_roles("guest")


@router.post("/requests", response_model=RequestOut)
async def submit(body: AskIn, actor: Actor = Depends(_guest),
                 s: AsyncSession = Depends(db_session)):
    """Intake → decompose → per-child triage (D35/D5). Identity/room/stay are
    ambient from the session, never asked (D3a)."""
    out = await intake.submit_request(s, actor, body.text)
    await s.commit()
    return out


@router.post("/children/{child_id}/confirm", response_model=ChildOut)
async def confirm(child_id: str, body: ConfirmIn,
                  actor: Actor = Depends(_guest),
                  s: AsyncSession = Depends(db_session)):
    """Guest has the final word on closure (D8)."""
    out = await intake.confirm(s, actor, _u.UUID(child_id), body.helpful)
    await s.commit()
    return out


# Distinct path from the dispatch status cards (GET /guest/requests, won by
# the dispatch router). Without this, the no-dispatch journey — grounded
# answers, smalltalk, and honest deferrals (D25) — is shadowed and invisible
# in the UI. Dispatch-mode children are intentionally skipped here: they are
# surfaced by the dispatch cards endpoint, so this stays the no-dispatch
# conversation surface only (no double-render).
@router.get("/conversation", response_model=list[RequestOut])
async def list_conversation(actor: Actor = Depends(_guest),
                            s: AsyncSession = Depends(db_session)):
    reqs = await rdal.list_requests_for_guest(s, actor.id)
    out = []
    for r in reqs:
        kids = await cdal.list_children_for_request(s, r.id)
        cs = []
        for c in kids:
            if c.fulfilment_mode == "dispatch":
                continue                       # surfaced by dispatch cards
            res = await resdal.get_resolution(s, c.id)
            cs.append(ChildOut(child_id=str(c.id), text=c.text,
                issue_code=None,
                terminal=("answered" if c.state in ("answered", "closed")
                          and res and res.mode in (
                              "grounded_answer", "reservation_mutation")
                          else "logged"),
                answer=(res.answer_text if res else None),
                closure_prompt=(c.state == "answered"),
                state=c.state))
        out.append(RequestOut(request_id=str(r.id), children=cs))
    return out
