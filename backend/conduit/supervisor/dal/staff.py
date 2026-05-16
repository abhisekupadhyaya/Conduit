# conduit/supervisor/dal/staff.py
from __future__ import annotations

import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from conduit.shared.models import (
    Account,
    Roster,
    RosterAssignment,
    StaffProfile,
    StaffSkill,
)


async def get_account(s: AsyncSession, account_id: uuid.UUID) -> Account | None:
    return await s.get(Account, account_id)


async def list_servicer_accounts(s: AsyncSession) -> list[Account]:
    r = await s.execute(
        select(Account)
        .where(Account.role == "servicer")
        .order_by(Account.display_name)
    )
    return list(r.scalars().all())


async def get_profile(
    s: AsyncSession, account_id: uuid.UUID
) -> StaffProfile | None:
    return await s.get(StaffProfile, account_id)


async def get_skills(s: AsyncSession, account_id: uuid.UUID) -> list[str]:
    r = await s.execute(
        select(StaffSkill.skill).where(StaffSkill.account_id == account_id)
    )
    return sorted(r.scalars().all())


async def get_assignments_with_roster(
    s: AsyncSession, account_id: uuid.UUID
) -> list[RosterAssignment]:
    """An account's ``RosterAssignment`` rows, each carrying a ``.roster``
    plain attribute so the pure ``shared.domain.availability`` contract
    (``assignment.roster`` with ``.shift_start/.shift_end/.status``) holds
    WITHOUT a model relationship (models out of scope).

    Task 5b (user-authorized scope add): the supervisor Staff page needs the
    SAME real derived availability the servicer home derives. ``RosterAssignment``
    has no ``roster`` ORM relationship (Task-2 modelled the staffing tables
    with explicit joins). This MIRRORS the established
    ``servicer/dal/self.py::get_assignments`` fetch-and-attach pattern —
    reimplemented here so the supervisor portal stays self-contained: it does
    NOT import ``conduit.servicer`` (the inverse of Resolution E /
    cross-portal import is forbidden). One batched roster query (no N+1),
    add-only / no flush / no commit (the merged DAL discipline; reads emit
    nothing)."""
    r = await s.execute(
        select(RosterAssignment).where(
            RosterAssignment.account_id == account_id
        )
    )
    assignments = list(r.scalars().all())
    if not assignments:
        return assignments
    roster_ids = {a.roster_id for a in assignments}
    rr = await s.execute(select(Roster).where(Roster.id.in_(roster_ids)))
    by_id = {ro.id: ro for ro in rr.scalars().all()}
    for a in assignments:
        a.roster = by_id.get(a.roster_id)
    return assignments


def add_profile(
    s: AsyncSession, account_id: uuid.UUID, staff_class: str
) -> StaffProfile:
    p = StaffProfile(account_id=account_id, staff_class=staff_class)
    s.add(p)
    return p


async def replace_skills(
    s: AsyncSession, account_id: uuid.UUID, skills: list[str]
) -> None:
    """The ONE sanctioned hard-replace in the codebase (spec §4).

    Not an HTTP DELETE - the 405 invariant is untouched. Skill rows are
    pure routing config, not FK-referenced by spine/provenance/read-model.
    """
    await s.execute(
        delete(StaffSkill).where(StaffSkill.account_id == account_id)
    )
    for sk in sorted(set(skills)):
        s.add(StaffSkill(account_id=account_id, skill=sk))
