# conduit/supervisor/services/rooms.py
from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from conduit.core.exceptions import ConflictError, NotFoundError, ValidationError
from conduit.supervisor.dal import rooms as dal
from conduit.supervisor.dal import sections as sdal


async def _require_section(s, section_id):
    if await sdal.get_section(s, section_id) is None:
        raise ValidationError("section does not exist")


async def list_rooms(s: AsyncSession, section_id: uuid.UUID | None = None):
    return await dal.list_rooms(s, section_id)


async def create_room(s: AsyncSession, label: str,
                        section_id: uuid.UUID, *, actor):
    await _require_section(s, section_id)
    if await dal.get_room_by_label(s, label) is not None:
        raise ConflictError("room label already exists")
    return await dal.insert_room(s, section_id, label)


async def update_room(s: AsyncSession, room_id: uuid.UUID, *,
                        label: str | None = None,
                        section_id: uuid.UUID | None = None, actor):
    room = await dal.get_room(s, room_id)
    if room is None:
        raise NotFoundError("room not found")
    if section_id is not None:
        await _require_section(s, section_id)
    if label is not None:
        dup = await dal.get_room_by_label(s, label)
        if dup is not None and dup.id != room.id:
            raise ConflictError("room label already exists")
    return await dal.update_room(s, room, label=label, section_id=section_id)
