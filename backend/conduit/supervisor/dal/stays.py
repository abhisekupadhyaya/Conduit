# conduit/supervisor/dal/stays.py
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from conduit.shared.models.stay import Stay


async def get_stay(s: AsyncSession, sid: uuid.UUID) -> Stay | None:
    return await s.get(Stay, sid)


async def get_active_stay_for_guest(
    s: AsyncSession, guest_account_id: uuid.UUID
) -> Stay | None:
    res = await s.execute(select(Stay).where(
        Stay.guest_account_id == guest_account_id,
        Stay.status == "active"))
    return res.scalar_one_or_none()


async def list_stays(
    s: AsyncSession, status: str | None = None,
    guest_id: uuid.UUID | None = None,
) -> list[Stay]:
    q = select(Stay).order_by(Stay.created_at.desc())
    if status is not None:
        q = q.where(Stay.status == status)
    if guest_id is not None:
        q = q.where(Stay.guest_account_id == guest_id)
    return list((await s.execute(q)).scalars().all())


async def insert_stay(
    s: AsyncSession, guest_account_id: uuid.UUID, room_id: uuid.UUID,
    check_in: datetime, check_out: datetime,
) -> Stay:
    st = Stay(guest_account_id=guest_account_id, room_id=room_id,
              check_in=check_in, check_out=check_out, status="active")
    s.add(st)
    return st


async def update_stay_fields(
    s: AsyncSession, stay: Stay, *,
    check_in: datetime | None = None, check_out: datetime | None = None,
) -> Stay:
    if check_in is not None:
        stay.check_in = check_in
    if check_out is not None:
        stay.check_out = check_out
    s.add(stay)
    return stay


async def set_stay_room(
    s: AsyncSession, stay: Stay, new_room_id: uuid.UUID
) -> Stay:
    stay.room_id = new_room_id
    s.add(stay)
    return stay


async def set_stay_status(
    s: AsyncSession, stay: Stay, status: str
) -> Stay:
    stay.status = status
    s.add(stay)
    return stay
