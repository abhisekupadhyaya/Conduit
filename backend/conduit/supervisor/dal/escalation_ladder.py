# conduit/supervisor/dal/escalation_ladder.py
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from conduit.shared.models import EscalationLadder


async def get(s: AsyncSession, id: uuid.UUID) -> EscalationLadder | None:
    return await s.get(EscalationLadder, id)


async def get_active(s: AsyncSession,
                     property_id: uuid.UUID) -> EscalationLadder | None:
    res = await s.execute(select(EscalationLadder).where(
        EscalationLadder.property_id == property_id,
        EscalationLadder.status == "active"))
    return res.scalars().first()


async def list_ladders(s: AsyncSession, status: str | None = None):
    q = select(EscalationLadder)
    if status:
        q = q.where(EscalationLadder.status == status)
    return (await s.execute(
        q.order_by(EscalationLadder.property_id))).scalars().all()


async def insert(s: AsyncSession, **f) -> EscalationLadder:
    obj = EscalationLadder(**f)
    s.add(obj)
    return obj


async def update(s: AsyncSession, obj: EscalationLadder,
                 **f) -> EscalationLadder:
    for k, v in f.items():
        if v is not None:
            setattr(obj, k, v)
    s.add(obj)
    return obj
