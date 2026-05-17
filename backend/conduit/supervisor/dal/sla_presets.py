# conduit/supervisor/dal/sla_presets.py
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from conduit.shared.models import SLAPreset


async def get(s: AsyncSession, id: uuid.UUID) -> SLAPreset | None:
    return await s.get(SLAPreset, id)


async def get_active(s: AsyncSession, property_id: uuid.UUID,
                     tier: str) -> SLAPreset | None:
    res = await s.execute(select(SLAPreset).where(
        SLAPreset.property_id == property_id,
        SLAPreset.tier == tier,
        SLAPreset.status == "active"))
    return res.scalars().first()


async def list_presets(s: AsyncSession, status: str | None = None):
    q = select(SLAPreset)
    if status:
        q = q.where(SLAPreset.status == status)
    return (await s.execute(
        q.order_by(SLAPreset.property_id, SLAPreset.tier))).scalars().all()


async def insert(s: AsyncSession, **f) -> SLAPreset:
    obj = SLAPreset(**f)
    s.add(obj)
    return obj


async def update(s: AsyncSession, obj: SLAPreset, **f) -> SLAPreset:
    for k, v in f.items():
        if v is not None:
            setattr(obj, k, v)
    s.add(obj)
    return obj
