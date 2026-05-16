# conduit/supervisor/api/staff.py
"""Supervisor Staff API. No DELETE -> 405 (D-series disable-not-delete;
``status=disabled`` is the "remove"). Mirrors issue_codes.py: per-handler
``_sup`` gate, edge ``await s.commit()`` on mutations only, reads never
commit; ORM/service-dict -> schema mapping at this layer only.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from conduit.core.deps import Actor, db_session, require_roles
from conduit.supervisor.schemas.staff import (
    CreateProfileIn,
    PatchProfileIn,
    SetSkillsIn,
    StaffOut,
)
from conduit.supervisor.services import staff as svc

router = APIRouter(prefix="/staff", tags=["supervisor-staff"])
_sup = require_roles("supervisor", "duty_manager")


@router.get("", response_model=list[StaffOut])
async def list_staff(
    status: str | None = None,
    class_: str | None = Query(default=None, alias="class"),
    actor: Actor = Depends(_sup),
    s: AsyncSession = Depends(db_session),
):
    rows = await svc.list_staff(s)
    out = []
    for r in rows:
        if status is not None and (
            r["profile"] is None or r["profile"]["status"] != status
        ):
            continue
        if class_ is not None and (
            r["profile"] is None or r["profile"]["staff_class"] != class_
        ):
            continue
        out.append(StaffOut.model_validate(r))
    return out


@router.get("/{account_id}", response_model=StaffOut)
async def get_staff(
    account_id: uuid.UUID,
    actor: Actor = Depends(_sup),
    s: AsyncSession = Depends(db_session),
):
    return StaffOut.model_validate(await svc.get_staff(s, account_id))


@router.post(
    "/{account_id}/profile", response_model=StaffOut, status_code=201
)
async def create_profile(
    account_id: uuid.UUID,
    body: CreateProfileIn,
    actor: Actor = Depends(_sup),
    s: AsyncSession = Depends(db_session),
):
    await svc.create_profile(
        s, actor.id, account_id, staff_class=body.staff_class
    )
    await s.commit()
    return StaffOut.model_validate(await svc.get_staff(s, account_id))


@router.patch("/{account_id}/profile", response_model=StaffOut)
async def patch_profile(
    account_id: uuid.UUID,
    body: PatchProfileIn,
    actor: Actor = Depends(_sup),
    s: AsyncSession = Depends(db_session),
):
    await svc.patch_profile(
        s, actor.id, account_id,
        staff_class=body.staff_class, status=body.status,
    )
    await s.commit()
    return StaffOut.model_validate(await svc.get_staff(s, account_id))


@router.put("/{account_id}/skills", response_model=StaffOut)
async def put_skills(
    account_id: uuid.UUID,
    body: SetSkillsIn,
    actor: Actor = Depends(_sup),
    s: AsyncSession = Depends(db_session),
):
    await svc.set_skills(s, actor.id, account_id, body.skills)
    await s.commit()
    return StaffOut.model_validate(await svc.get_staff(s, account_id))
