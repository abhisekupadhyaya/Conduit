"""Supervisor account management API. No DELETE — D29 (disable, never delete)."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from conduit.core.deps import Actor, db_session, require_roles
from conduit.supervisor.schemas.accounts import (
    AccountCreateIn,
    AccountOut,
    AccountUpdateIn,
)
from conduit.supervisor.services import accounts as svc

router = APIRouter(prefix="/accounts", tags=["supervisor-accounts"])
_sup = require_roles("supervisor", "duty_manager")


@router.get("", response_model=list[AccountOut])
async def list_accounts(role: str | None = None, status: str | None = None,
                        actor: Actor = Depends(_sup),
                        s: AsyncSession = Depends(db_session)):
    return [AccountOut.model_validate(a)
            for a in await svc.list_accounts(s, role=role, status=status)]


@router.post("", response_model=AccountOut, status_code=201)
async def create_account(body: AccountCreateIn, actor: Actor = Depends(_sup),
                         s: AsyncSession = Depends(db_session)):
    a = await svc.create_account(
        s, role=body.role, username=body.username,
        display_name=body.display_name, password=body.password)
    await s.commit()
    return AccountOut.model_validate(a)


@router.patch("/{account_id}", response_model=AccountOut)
async def update_account(account_id: uuid.UUID, body: AccountUpdateIn,
                         actor: Actor = Depends(_sup),
                         s: AsyncSession = Depends(db_session)):
    patch = body.model_dump(exclude_none=True)
    a = await svc.update_account(s, actor, account_id, patch)
    await s.commit()
    return AccountOut.model_validate(a)
