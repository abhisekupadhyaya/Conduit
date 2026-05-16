# conduit/supervisor/dal/kb.py
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from conduit.shared.models import KBEntry


async def get(s: AsyncSession, id: uuid.UUID) -> KBEntry | None:
    return await s.get(KBEntry, id)


async def list_entries(s: AsyncSession, status: str | None = None):
    q = select(KBEntry)
    if status:
        q = q.where(KBEntry.status == status)
    return (await s.execute(q.order_by(KBEntry.created_at))).scalars().all()


async def insert(s: AsyncSession, **f) -> KBEntry:
    obj = KBEntry(**f)
    s.add(obj)
    return obj


async def update(s: AsyncSession, obj: KBEntry, **f) -> KBEntry:
    for k, v in f.items():
        if v is not None:
            setattr(obj, k, v)
    s.add(obj)
    return obj
