# conduit/guest/dal/requests.py
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from conduit.shared.models import Request


async def insert_request(s: AsyncSession, *, guest_account_id, stay_id,
                          raw_text, channel="text") -> Request:
    obj = Request(guest_account_id=guest_account_id, stay_id=stay_id,
                  raw_text=raw_text, channel=channel)
    s.add(obj)
    return obj


async def get_request(s: AsyncSession, id: uuid.UUID) -> Request | None:
    return await s.get(Request, id)


async def list_requests_for_guest(s: AsyncSession, guest_account_id: uuid.UUID):
    res = await s.execute(select(Request)
        .where(Request.guest_account_id == guest_account_id)
        .order_by(Request.created_at))
    return res.scalars().all()
