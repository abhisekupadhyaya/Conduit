"""Supervisor awareness stream — the FIRST event read model (Spec §8/§9).

ONE composite polled (AD7) projection over the append-only
``event``+detail log: incoming · task delegation · servicer recent work ·
open glitches. This is the DEFERRED read side finally consumed — every
item is computed FROM the event log (the glitch set is glitch_opened
MINUS glitch_closed; it disappears once closed), NOT a direct core-table
SELECT that bypasses the log.

Per-handler ``require_roles("supervisor","duty_manager")`` (server-side
regardless of client — guest/servicer → 403, no cookie → 401). This is a
WATCH-ONLY surface, deliberately DISTINCT from the E3 decision queue
(D2 — watch vs act; the two are separate routes, never folded together).
A read: it NEVER commits, never writes. There is deliberately NO
``DELETE`` handler, so DELETE → 405. A malformed query is rejected by the
``extra="forbid"`` schema.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from conduit.core.deps import Actor, db_session, require_roles
from conduit.supervisor.dal import awareness as dal
from conduit.supervisor.schemas.awareness import AwarenessOut

router = APIRouter(tags=["supervisor-awareness"])
_sup = require_roles("supervisor", "duty_manager")


@router.get("/awareness", response_model=AwarenessOut)
async def awareness(actor: Actor = Depends(_sup),
                    s: AsyncSession = Depends(db_session)):
    """The ONE composite projection of the four sections, derived FROM the
    append-only ``event``+detail log. Polled (AD7). A read — it never
    commits."""
    return await dal.awareness(s)
