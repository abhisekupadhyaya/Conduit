# conduit/supervisor/dal/rooms.py
from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from conduit.shared.models.room import Room


async def get_room(s: AsyncSession, rid: uuid.UUID) -> Room | None:
    return await s.get(Room, rid)


async def get_room_by_label(s: AsyncSession, label: str) -> Room | None:
    res = await s.execute(select(Room).where(
        func.lower(Room.label) == label.lower()))
    return res.scalar_one_or_none()


async def list_rooms(
    s: AsyncSession, section_id: uuid.UUID | None = None
) -> list[Room]:
    q = select(Room).order_by(func.lower(Room.label))
    if section_id is not None:
        q = q.where(Room.section_id == section_id)
    return list((await s.execute(q)).scalars().all())


async def insert_room(
    s: AsyncSession, section_id: uuid.UUID, label: str
) -> Room:
    r = Room(section_id=section_id, label=label)
    s.add(r)
    return r


async def update_room(
    s: AsyncSession, room: Room, *,
    label: str | None = None, section_id: uuid.UUID | None = None,
) -> Room:
    if label is not None:
        room.label = label
    if section_id is not None:
        room.section_id = section_id
    s.add(room)
    return room
