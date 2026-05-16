"""Decision queue — the D9 time-boxed checkpoints (Spec §8 / §7.4 / §9.2).

Three triggers land here (D20): triage-flag, stall, servicer-raised. Each
with an AI recommendation + supervisor-SLA countdown DEADLINE; silence →
auto-proceed (D9, the engine path — NOT an API call); bounded backstop →
duty manager (D21).

Per-handler ``require_roles("supervisor","duty_manager")`` (server-side
regardless of client). The resolve handler commits at the edge; the queue
read NEVER commits. ``resolve`` is a dedicated ACTION endpoint
(``/decisions/{id}/resolve``) — not a generic PATCH — and there is
deliberately NO ``DELETE`` handler, so DELETE → 405. Domain errors raised
by the service (merged ``core/exceptions``) are mapped to 403 / 409 / 422
by the merged ``install_exception_handlers``; a malformed body is rejected
by the ``extra="forbid"`` schema → 422.

silence ≡ approve is STRUCTURAL: this handler only maps action→outcome and
passes the supervisor as actor; the SAME ``spine.apply_recommendation`` is
the executor for both this path and the engine auto-proceed (D2/D3) — no
resolution logic is reimplemented and no parallel writer is added.
"""
from __future__ import annotations

import uuid as _u

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from conduit.core.deps import Actor, db_session, require_roles
from conduit.supervisor.schemas.decisions import (DecisionOut, ResolveIn,
                                                  ResolveOut)
from conduit.supervisor.services import decisions as svc

router = APIRouter(tags=["supervisor-decisions"])
_sup = require_roles("supervisor", "duty_manager")


@router.get("/decisions", response_model=list[DecisionOut])
async def decision_queue(status: str | None = None,
                         actor: Actor = Depends(_sup),
                         s: AsyncSession = Depends(db_session)):
    """The decision queue: open escalations (default) + their AI
    recommendation + per-action detail + the supervisor-SLA countdown
    deadline + ``cycle_count``; a duty-manager hard-escalation is flagged
    ``non_time_boxed`` (D21). A read — it never commits."""
    return await svc.list_decisions(s, status=status)


@router.post("/decisions/{escalation_id}/resolve",
             response_model=ResolveOut)
async def resolve(escalation_id: str, body: ResolveIn,
                  actor: Actor = Depends(_sup),
                  s: AsyncSession = Depends(db_session)):
    """Approve / edit / override (D9 / §7.4) — THE single human resolve
    path. Maps action→outcome and calls ``spine.apply_recommendation``
    (the only executor) with the supervisor as actor. Already resolved →
    409; malformed edit/override → 422."""
    out = await svc.resolve(s, actor, _u.UUID(escalation_id),
                            action=body.action, payload=body.payload)
    await s.commit()
    return out
