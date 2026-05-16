# conduit/supervisor/dal/staff.py
from __future__ import annotations

import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from conduit.shared.models import Account, StaffProfile, StaffSkill


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
