# conduit/guest/dal/children.py
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from conduit.shared.models import ChildSubRequest, Request


async def insert_child(s: AsyncSession, **f) -> ChildSubRequest:
    obj = ChildSubRequest(**f)
    s.add(obj)
    return obj


async def get_child(s: AsyncSession, id: uuid.UUID) -> ChildSubRequest | None:
    return await s.get(ChildSubRequest, id)


async def list_children_for_request(s: AsyncSession, request_id: uuid.UUID):
    res = await s.execute(select(ChildSubRequest)
        .where(ChildSubRequest.request_id == request_id)
        .order_by(ChildSubRequest.created_at))
    return res.scalars().all()


async def list_children_for_guest(s: AsyncSession,
                                   guest_account_id: uuid.UUID):
    res = await s.execute(select(ChildSubRequest)
        .join(Request, ChildSubRequest.request_id == Request.id)
        .where(Request.guest_account_id == guest_account_id)
        .order_by(ChildSubRequest.created_at))
    return res.scalars().all()
