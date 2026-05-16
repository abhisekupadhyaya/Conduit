# conduit/supervisor/dal/sections.py
from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from conduit.shared.models.room import Room
from conduit.shared.models.section import Section


async def get_section(s: AsyncSession, sid: uuid.UUID) -> Section | None:
    return await s.get(Section, sid)


async def get_section_by_label(
    s: AsyncSession, property_id: uuid.UUID, label: str
) -> Section | None:
    res = await s.execute(select(Section).where(
        Section.property_id == property_id,
        func.lower(Section.label) == label.lower()))
    return res.scalar_one_or_none()


async def list_sections_with_room_counts(
    s: AsyncSession,
) -> list[tuple[Section, int]]:
    res = await s.execute(
        select(Section, func.count(Room.id))
        .outerjoin(Room, Room.section_id == Section.id)
        .group_by(Section.id).order_by(func.lower(Section.label)))
    return [(sec, int(c)) for sec, c in res.all()]


async def insert_section(
    s: AsyncSession, property_id: uuid.UUID, label: str
) -> Section:
    sec = Section(property_id=property_id, label=label)
    s.add(sec)
    return sec


async def update_section(
    s: AsyncSession, section: Section, *, label: str
) -> Section:
    section.label = label
    s.add(section)
    return section
