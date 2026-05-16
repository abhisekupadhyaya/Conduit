"""Servicer working surface: queue + task actions."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from conduit.core.deps import Actor, require_roles

router = APIRouter(tags=["servicer-queue"])
_svc = require_roles("servicer")


@router.get("/queue")
async def queue(actor: Actor = Depends(_svc)) -> dict[str, str]:
    """Pushed (owned, D12/D18) + claimable (claim-fallback, D12) tasks, each
    with accept-window + SLA countdown (D23)."""
    raise NotImplementedError


@router.post("/work-orders/{wo_id}/accept")
async def accept(wo_id: str, actor: Actor = Depends(_svc)) -> dict[str, str]:
    """Accept stops the accept-window timer; fulfilment SLA keeps running (D23)."""
    raise NotImplementedError


@router.post("/work-orders/{wo_id}/escalate")
async def escalate(wo_id: str, actor: Actor = Depends(_svc)) -> dict[str, str]:
    """Raise a mid-lifecycle escalation (D20 trigger 3) — don't improvise."""
    raise NotImplementedError
