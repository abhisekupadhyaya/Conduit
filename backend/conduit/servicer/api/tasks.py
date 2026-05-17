"""Servicer task surface (Spec §8 / §9.2): the polled task queue + the
guarded servicer actions (claim / accept / start / complete / raise).

Per-handler ``require_roles("servicer")`` (server-side regardless of
client). Mutating handlers commit at the edge; the queue read NEVER
commits. Domain errors raised by the service (merged ``core/exceptions``)
are mapped to 403 / 404 / 409 / 422 by the merged
``install_exception_handlers``. The guarded transitions are dedicated
ACTION endpoints (not a generic PATCH) — there is deliberately NO
``DELETE`` handler, so DELETE → 405. ``raise`` opens a D20 escalation →
201.
"""
from __future__ import annotations

import uuid as _u

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from conduit.core.deps import Actor, db_session, require_roles
from conduit.servicer.schemas.tasks import CompleteIn, RaiseIn, TaskOut
from conduit.servicer.services import tasks as svc

router = APIRouter(tags=["servicer-tasks"])
_svc = require_roles("servicer")


@router.get("/tasks", response_model=list[TaskOut])
async def list_tasks(actor: Actor = Depends(_svc),
                     s: AsyncSession = Depends(db_session)):
    """Polled task queue, self-scoped to the caller — pushed (owned) +
    claimable (in-zone broadcast) with live SLA / accept-window deadlines
    (D23). A read — it never commits."""
    return await svc.list_tasks(s, actor)


@router.post("/tasks/{wo_id}/claim")
async def claim(wo_id: str, actor: Actor = Depends(_svc),
                s: AsyncSession = Depends(db_session)):
    """Claim a broadcast task (D12). Not claimable → 409; not in zone →
    403. ``accountable_owner_id`` is UNCHANGED (D12)."""
    out = await svc.claim(s, actor, _u.UUID(wo_id))
    await s.commit()
    return out


@router.post("/tasks/{wo_id}/accept")
async def accept(wo_id: str, actor: Actor = Depends(_svc),
                 s: AsyncSession = Depends(db_session)):
    """Accept → stops the accept-window timer; fulfilment SLA runs on (D23)."""
    out = await svc.accept(s, actor, _u.UUID(wo_id))
    await s.commit()
    return out


@router.post("/tasks/{wo_id}/start")
async def start(wo_id: str, actor: Actor = Depends(_svc),
                s: AsyncSession = Depends(db_session)):
    """Begin work → ``in_progress``."""
    out = await svc.start(s, actor, _u.UUID(wo_id))
    await s.commit()
    return out


@router.post("/tasks/{wo_id}/complete")
async def complete(wo_id: str, body: CompleteIn,
                   actor: Actor = Depends(_svc),
                   s: AsyncSession = Depends(db_session)):
    """Complete (optional ``notes``) → the C4 hop drives the child to
    ``done_pending_confirm`` (D14)."""
    out = await svc.complete(s, actor, _u.UUID(wo_id), body.notes)
    await s.commit()
    return out


@router.post("/tasks/{wo_id}/raise", status_code=201)
async def raise_escalation(wo_id: str, body: RaiseIn,
                           actor: Actor = Depends(_svc),
                           s: AsyncSession = Depends(db_session)):
    """D20 servicer-raised mid-lifecycle escalation via the spine → 201."""
    out = await svc.raise_escalation(s, actor, _u.UUID(wo_id), body.reason)
    await s.commit()
    return out
