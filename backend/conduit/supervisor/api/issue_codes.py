# conduit/supervisor/api/issue_codes.py
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from conduit.core.deps import Actor, db_session, require_roles
from conduit.supervisor.schemas.issue_code import (
    IssueCodeCreate,
    IssueCodeOut,
    IssueCodePatch,
)
from conduit.supervisor.services import issue_codes as svc

router = APIRouter(tags=["supervisor-issue-codes"])
_sup = require_roles("supervisor", "duty_manager")


@router.get("/issue-codes", response_model=list[IssueCodeOut])
async def list_codes(status: str | None = None,
                     actor: Actor = Depends(_sup),
                     s: AsyncSession = Depends(db_session)):
    return await svc.list_codes(s, status=status)


@router.post("/issue-codes", response_model=IssueCodeOut, status_code=201)
async def create_code(body: IssueCodeCreate, actor: Actor = Depends(_sup),
                      s: AsyncSession = Depends(db_session)):
    obj = await svc.create_code(s, actor=actor, **body.model_dump())
    await s.commit()
    return obj


@router.patch("/issue-codes/{code_id}", response_model=IssueCodeOut)
async def patch_code(code_id: uuid.UUID, body: IssueCodePatch,
                     actor: Actor = Depends(_sup),
                     s: AsyncSession = Depends(db_session)):
    obj = await svc.update_code(s, code_id, actor=actor,
                                **body.model_dump(exclude_unset=True))
    await s.commit()
    return obj
