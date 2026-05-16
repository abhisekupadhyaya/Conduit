"""The conversation IS the guest portal: ask + status + confirm."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from conduit.core.deps import Actor, require_roles

router = APIRouter(tags=["guest-conversation"])
_guest = require_roles("guest")


class AskIn(BaseModel):
    text: str


@router.post("/requests")
async def submit(_: AskIn, actor: Actor = Depends(_guest)) -> dict[str, str]:
    """Intake → decompose → per-child triage (D35/D5). Identity/room/stay are
    ambient from the session, never asked (D3a)."""
    raise NotImplementedError


@router.post("/children/{child_id}/confirm")
async def confirm(child_id: str, actor: Actor = Depends(_guest)) -> dict[str, str]:
    """Guest has the final word on closure (D8)."""
    raise NotImplementedError
