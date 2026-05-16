# conduit/supervisor/api/rosters.py
"""Supervisor Rosters API. No DELETE -> 405 (cross-slice disable-not-delete
invariant; ``status=disabled`` is the "remove"). Mirrors Task 5's
``staff.py``/``issue_codes.py``: short ``/rosters`` prefix, per-handler
``_sup`` gate, edge ``await s.commit()`` on mutating handlers only, reads
never commit; ORM -> schema mapping at this layer only. Single-property
(AD9) resolved exactly the way ``api/binding.py`` resolves it.
"""
from __future__ import annotations

import datetime as dt
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from conduit.core.deps import Actor, db_session, require_roles
from conduit.shared.models import Property
from conduit.supervisor.schemas.roster import (
    AssignmentOut,
    CreateAssignmentIn,
    CreateRosterIn,
    PatchAssignmentIn,
    PatchRosterIn,
    RosterOut,
)
from conduit.supervisor.services import rosters as svc

router = APIRouter(prefix="/rosters", tags=["supervisor-rosters"])
_sup = require_roles("supervisor", "duty_manager")


async def _property_id(s: AsyncSession) -> uuid.UUID:
    return (await s.execute(select(Property.id))).scalars().first()


def _roster_out(r) -> RosterOut:
    return RosterOut(
        id=r.id,
        shift_start=r.shift_start,
        shift_end=r.shift_end,
        status=r.status,
    )


def _assignment_out(a) -> AssignmentOut:
    return AssignmentOut(
        id=a.id,
        roster_id=a.roster_id,
        account_id=a.account_id,
        section_id=a.section_id,
        assignment=a.assignment,
        status=a.status,
    )


@router.get("", response_model=list[RosterOut])
async def list_rosters(
    status: str | None = None,
    active_at: dt.datetime | None = None,
    actor: Actor = Depends(_sup),
    s: AsyncSession = Depends(db_session),
):
    rows = await svc.list_rosters(s, status=status, active_at=active_at)
    return [_roster_out(r) for r in rows]


@router.post("", response_model=RosterOut, status_code=201)
async def create_roster(
    body: CreateRosterIn,
    actor: Actor = Depends(_sup),
    s: AsyncSession = Depends(db_session),
):
    r = await svc.create_roster(
        s,
        actor.id,
        await _property_id(s),
        body.shift_start,
        body.shift_end,
    )
    await s.commit()
    return _roster_out(r)


@router.patch("/{roster_id}", response_model=RosterOut)
async def patch_roster(
    roster_id: uuid.UUID,
    body: PatchRosterIn,
    actor: Actor = Depends(_sup),
    s: AsyncSession = Depends(db_session),
):
    r = await svc.update_roster(
        s,
        actor.id,
        roster_id,
        shift_start=body.shift_start,
        shift_end=body.shift_end,
        status=body.status,
    )
    await s.commit()
    return _roster_out(r)


@router.get(
    "/{roster_id}/assignments", response_model=list[AssignmentOut]
)
async def list_assignments(
    roster_id: uuid.UUID,
    actor: Actor = Depends(_sup),
    s: AsyncSession = Depends(db_session),
):
    rows = await svc.list_assignments(s, roster_id)
    return [_assignment_out(a) for a in rows]


@router.post(
    "/{roster_id}/assignments",
    response_model=AssignmentOut,
    status_code=201,
)
async def create_assignment(
    roster_id: uuid.UUID,
    body: CreateAssignmentIn,
    actor: Actor = Depends(_sup),
    s: AsyncSession = Depends(db_session),
):
    a = await svc.create_assignment(
        s,
        actor.id,
        roster_id,
        account_id=body.account_id,
        section_id=body.section_id,
        assignment=body.assignment,
    )
    await s.commit()
    return _assignment_out(a)


@router.patch(
    "/{roster_id}/assignments/{assignment_id}",
    response_model=AssignmentOut,
)
async def patch_assignment(
    roster_id: uuid.UUID,
    assignment_id: uuid.UUID,
    body: PatchAssignmentIn,
    actor: Actor = Depends(_sup),
    s: AsyncSession = Depends(db_session),
):
    a = await svc.update_assignment(
        s,
        actor.id,
        roster_id,
        assignment_id,
        section_id=body.section_id,
        assignment=body.assignment,
        status=body.status,
    )
    await s.commit()
    return _assignment_out(a)
