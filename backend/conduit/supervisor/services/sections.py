# conduit/supervisor/services/sections.py
from __future__ import annotations
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from conduit.core.exceptions import ConflictError, NotFoundError
from conduit.supervisor.dal import sections as dal


async def list_sections(s: AsyncSession):
    return await dal.list_sections_with_room_counts(s)


async def create_section(s: AsyncSession, property_id: uuid.UUID,
                          label: str, *, actor):
    if await dal.get_section_by_label(s, property_id, label) is not None:
        raise ConflictError("section label already exists")
    return await dal.insert_section(s, property_id, label)


async def rename_section(s: AsyncSession, section_id: uuid.UUID,
                          label: str, *, actor):
    sec = await dal.get_section(s, section_id)
    if sec is None:
        raise NotFoundError("section not found")
    dup = await dal.get_section_by_label(s, sec.property_id, label)
    if dup is not None and dup.id != sec.id:
        raise ConflictError("section label already exists")
    return await dal.update_section(s, sec, label=label)
