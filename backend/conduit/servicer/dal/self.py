# conduit/servicer/dal/self.py
"""Self-scoped servicer reads + the single presence write.

Resolution E (spec §4 "Portal ownership"): the servicer owns its own reads
and presence through THIS module; it must NOT import ``supervisor/dal``.
Every query is filtered by the authenticated ``account_id``.

``RosterAssignment`` has no ``roster`` ORM relationship (Task-2 modelled the
staffing tables with explicit joins, no relationships). The pure
``shared.domain.availability`` predicate requires ``assignment.roster`` with
``.shift_start/.shift_end/.status``. We satisfy that contract WITHOUT adding a
model relationship (models out of scope this task): fetch the assignments,
fetch their rosters by id in one query, and attach the ``Roster`` ORM object
onto each assignment as a plain Python attribute (``a.roster = roster``).
Add-only/no-flush/no-commit (the merged DAL discipline).
"""
from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from conduit.shared.models import (
    Roster,
    RosterAssignment,
    Section,
    StaffProfile,
    StaffSkill,
)


async def get_profile(
    s: AsyncSession, account_id: uuid.UUID
) -> StaffProfile | None:
    return await s.get(StaffProfile, account_id)


async def get_skills(s: AsyncSession, account_id: uuid.UUID) -> list[str]:
    r = await s.execute(
        select(StaffSkill.skill).where(StaffSkill.account_id == account_id)
    )
    return sorted(r.scalars().all())


async def get_assignments(
    s: AsyncSession, account_id: uuid.UUID
) -> list[RosterAssignment]:
    """Self-scoped assignments, each carrying a ``.roster`` plain attribute
    so the pure availability contract (``assignment.roster``) holds without a
    model relationship."""
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


async def get_section_label(
    s: AsyncSession, section_id: uuid.UUID | None
) -> str | None:
    if section_id is None:
        return None
    sec = await s.get(Section, section_id)
    return None if sec is None else sec.label


async def set_presence(
    s: AsyncSession,
    account_id: uuid.UUID,
    presence: str,
    set_at: dt.datetime,
) -> StaffProfile:
    p = await s.get(StaffProfile, account_id)
    p.presence = presence
    p.presence_set_at = set_at
    return p
