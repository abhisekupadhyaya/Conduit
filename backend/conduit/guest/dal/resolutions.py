# conduit/guest/dal/resolutions.py
from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from conduit.shared.models import (
    NDProvenanceField,
    NDProvenanceKB,
    NoDispatchResolution,
)


async def insert_resolution(s: AsyncSession, *, child_id, mode,
                            answer_text=None) -> NoDispatchResolution:
    obj = NoDispatchResolution(child_id=child_id, mode=mode,
                               answer_text=answer_text)
    s.add(obj)
    return obj


async def get_resolution(s: AsyncSession,
                         child_id: uuid.UUID) -> NoDispatchResolution | None:
    return await s.get(NoDispatchResolution, child_id)


async def set_helpful(s: AsyncSession, res: NoDispatchResolution,
                      helpful) -> NoDispatchResolution:
    res.helpful = helpful
    s.add(res)
    return res


async def insert_provenance_kb(s: AsyncSession, child_id, kb_entry_id,
                               claimed_used) -> NDProvenanceKB:
    obj = NDProvenanceKB(resolution_child_id=child_id, kb_entry_id=kb_entry_id,
                         claimed_used=claimed_used)
    s.add(obj)
    return obj


async def insert_provenance_field(s: AsyncSession, child_id, field_name,
                                   claimed_used) -> NDProvenanceField:
    obj = NDProvenanceField(resolution_child_id=child_id,
                            field_name=field_name, claimed_used=claimed_used)
    s.add(obj)
    return obj
