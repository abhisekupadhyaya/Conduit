# conduit/supervisor/api/kb.py
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from conduit.core.deps import Actor, db_session, require_roles
from conduit.supervisor.schemas.kb import (
    KBEntryCreate,
    KBEntryOut,
    KBEntryPatch,
)
from conduit.supervisor.services import kb as svc

router = APIRouter(tags=["supervisor-kb"])
_sup = require_roles("supervisor", "duty_manager")


@router.get("/kb", response_model=list[KBEntryOut])
async def list_entries(status: str | None = None,
                       actor: Actor = Depends(_sup),
                       s: AsyncSession = Depends(db_session)):
    return await svc.list_entries(s, status=status)


@router.post("/kb", response_model=KBEntryOut, status_code=201)
async def create_entry(body: KBEntryCreate, actor: Actor = Depends(_sup),
                       s: AsyncSession = Depends(db_session)):
    obj = await svc.create_entry(s, actor=actor, **body.model_dump())
    await s.commit()
    return obj


@router.patch("/kb/{kid}", response_model=KBEntryOut)
async def patch_entry(kid: uuid.UUID, body: KBEntryPatch,
                      actor: Actor = Depends(_sup),
                      s: AsyncSession = Depends(db_session)):
    obj = await svc.update_entry(s, kid, actor=actor,
                                 **body.model_dump(exclude_unset=True))
    await s.commit()
    return obj
