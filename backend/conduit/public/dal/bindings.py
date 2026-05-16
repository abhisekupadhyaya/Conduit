# conduit/public/dal/bindings.py
from __future__ import annotations
import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from conduit.shared.models.room import Room
from conduit.shared.models.section import Section
from conduit.shared.models.stay import Stay


async def get_active_binding_for_guest(
    s: AsyncSession, guest_account_id: uuid.UUID
) -> tuple[Stay, Room, Section] | None:
    res = await s.execute(
        select(Stay, Room, Section)
        .join(Room, Room.id == Stay.room_id)
        .join(Section, Section.id == Room.section_id)
        .where(Stay.guest_account_id == guest_account_id,
               Stay.status == "active"))
    row = res.first()
    return None if row is None else (row[0], row[1], row[2])
