"""Supervisor task explorer + override — the D6 god-mode (Spec §8
"Supervisor children/override").

Per-handler ``require_roles("supervisor","duty_manager")`` (server-side
regardless of client — guest/servicer → 403, no cookie → 401). The
explorer ``GET`` is global by role (the supervisor sees everything — NOT
self-scoped) and NEVER commits. The three override actions
(``takeover``/``reassign``/``cancel``) are dedicated ACTION endpoints and
commit at the edge. There is deliberately NO ``DELETE`` handler, so
DELETE → 405. A malformed body is rejected by the ``extra="forbid"``
schema → 422. Domain errors raised by the service (merged
``core/exceptions``) are mapped to 404 / 409 by the merged
``install_exception_handlers``.

D6 god-mode is the SAME guarded machinery as everywhere — the service
effects via the C4 ``lifecycle.transition`` single writer (cancel) and
the established D2/D6 in-place WorkOrder assignee mutation
(takeover/reassign). No bypass node; no parallel writer (see
``services/override.py``).
"""
from __future__ import annotations

import uuid as _u

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from conduit.core.deps import Actor, db_session, require_roles
from conduit.supervisor.schemas.override import (CancelIn, ChildExplorerOut,
                                                 OverrideOut, ReassignIn,
                                                 TakeoverIn)
from conduit.supervisor.services import override as svc

router = APIRouter(tags=["supervisor-children"])
_sup = require_roles("supervisor", "duty_manager")


@router.get("/children", response_model=list[ChildExplorerOut])
async def children_explorer(child_id: str | None = None,
                            state: str | None = None,
                            actor: Actor = Depends(_sup),
                            s: AsyncSession = Depends(db_session)):
    """The global task explorer: ANY child in ANY state + its WorkOrder /
    Escalation / Glitch, optionally filtered by ``?child_id`` / ``?state``.
    Supervisor scope is global by role (Spec §8). A read — never commits."""
    cid = _u.UUID(child_id) if child_id else None
    return await svc.list_children(s, child_id=cid, state=state)


@router.post("/children/{child_id}/takeover",
             response_model=OverrideOut)
async def takeover(child_id: str, body: TakeoverIn,
                   actor: Actor = Depends(_sup),
                   s: AsyncSession = Depends(db_session)):
    """D6 takeover (from ANY active state). In-place assignee swap; commits
    at the edge."""
    out = await svc.takeover(s, actor, _u.UUID(child_id),
                             target_servicer_id=body.target_servicer_id)
    await s.commit()
    return out


@router.post("/children/{child_id}/reassign",
             response_model=OverrideOut)
async def reassign(child_id: str, body: ReassignIn,
                   actor: Actor = Depends(_sup),
                   s: AsyncSession = Depends(db_session)):
    """D6 reassign (from ANY active state) to an explicit target. In-place
    assignee swap; commits at the edge."""
    out = await svc.reassign(s, actor, _u.UUID(child_id),
                             target_servicer_id=body.target_servicer_id)
    await s.commit()
    return out


@router.post("/children/{child_id}/cancel",
             response_model=OverrideOut)
async def cancel(child_id: str, body: CancelIn,
                 actor: Actor = Depends(_sup),
                 s: AsyncSession = Depends(db_session)):
    """D6 cancel — the supervisor interrupt via the C4 single writer
    (``child -> cancelled``, legal from any active state; an already
    -terminal child → 409). Commits at the edge."""
    out = await svc.cancel(s, actor, _u.UUID(child_id))
    await s.commit()
    return out
