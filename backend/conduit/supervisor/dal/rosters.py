# conduit/supervisor/dal/rosters.py
"""Supervisor Rosters DAL — add-only / no-flush / no-commit (spec §4
layering, identical to Task 5's ``dal/staff.py``). ``select``/``s.add``
only; services own the flush, the API handler commits at the edge.

The D18 cross-table guard needs the servicer's ``StaffProfile``; that query
already lives in Task 5's ``dal.staff.get_profile`` — it is re-exposed here
(re-export, NOT re-implemented) so the rosters service stays one-layer-deep
without duplicating the profile query.
"""
from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from conduit.shared.models import Account, Roster, RosterAssignment
from conduit.supervisor.dal.staff import get_profile  # D18 guard — reused

__all__ = [
    "add_assignment",
    "add_roster",
    "get_account",
    "get_assignment",
    "get_profile",
    "get_roster",
    "list_assignments",
    "list_rosters",
]


async def get_account(s: AsyncSession, account_id: uuid.UUID) -> Account | None:
    return await s.get(Account, account_id)


def add_roster(
    s: AsyncSession,
    property_id: uuid.UUID,
    shift_start: dt.datetime,
    shift_end: dt.datetime,
) -> Roster:
    r = Roster(
        property_id=property_id,
        shift_start=shift_start,
        shift_end=shift_end,
    )
    s.add(r)
    return r


async def get_roster(
    s: AsyncSession, roster_id: uuid.UUID
) -> Roster | None:
    return await s.get(Roster, roster_id)


async def list_rosters(
    s: AsyncSession,
    status: str | None = None,
    active_at: dt.datetime | None = None,
) -> list[Roster]:
    q = select(Roster)
    if status is not None:
        q = q.where(Roster.status == status)
    if active_at is not None:
        q = q.where(
            Roster.shift_start <= active_at,
            Roster.shift_end > active_at,
        )
    q = q.order_by(Roster.shift_start)
    r = await s.execute(q)
    return list(r.scalars().all())


async def list_assignments(
    s: AsyncSession, roster_id: uuid.UUID
) -> list[RosterAssignment]:
    r = await s.execute(
        select(RosterAssignment)
        .where(RosterAssignment.roster_id == roster_id)
        .order_by(RosterAssignment.created_at)
    )
    return list(r.scalars().all())


async def get_assignment(
    s: AsyncSession, assignment_id: uuid.UUID
) -> RosterAssignment | None:
    return await s.get(RosterAssignment, assignment_id)


def add_assignment(
    s: AsyncSession,
    roster_id: uuid.UUID,
    account_id: uuid.UUID,
    section_id: uuid.UUID | None,
    assignment: str,
) -> RosterAssignment:
    a = RosterAssignment(
        roster_id=roster_id,
        account_id=account_id,
        section_id=section_id,
        assignment=assignment,
    )
    s.add(a)
    return a
