"""Decision queue — the D9 time-boxed checkpoints.

Three triggers land here (D20): triage-flag, stall, servicer-raised. Each with
an AI recommendation + supervisor-SLA countdown; silence → auto-proceed (D9);
bounded backstop → duty manager (D21).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from conduit.core.deps import Actor, require_roles

router = APIRouter(tags=["supervisor-decisions"])
_sup = require_roles("supervisor", "duty_manager")


@router.get("/decisions")
async def decision_queue(actor: Actor = Depends(_sup)) -> dict[str, str]:
    raise NotImplementedError


@router.post("/decisions/{escalation_id}")
async def resolve(escalation_id: str, actor: Actor = Depends(_sup)) -> dict[str, str]:
    """Approve / edit / override (D9)."""
    raise NotImplementedError
