# conduit/supervisor/dal/issue_codes.py
from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from conduit.shared.models import IssueCode


async def get(s: AsyncSession, id: uuid.UUID) -> IssueCode | None:
    return await s.get(IssueCode, id)


async def get_by_code(s: AsyncSession, code: str) -> IssueCode | None:
    res = await s.execute(select(IssueCode)
        .where(func.lower(IssueCode.code) == code.lower()))
    return res.scalars().first()


async def list_codes(s: AsyncSession, status: str | None = None,
                     origin: str | None = None):
    q = select(IssueCode)
    if status:
        q = q.where(IssueCode.status == status)
    if origin:
        q = q.where(IssueCode.origin == origin)
    return (await s.execute(q.order_by(IssueCode.code))).scalars().all()


async def insert(s: AsyncSession, **f) -> IssueCode:
    obj = IssueCode(**f)
    s.add(obj)
    return obj


async def update(s: AsyncSession, obj: IssueCode, **f) -> IssueCode:
    for k, v in f.items():
        if v is not None:
            setattr(obj, k, v)
    s.add(obj)
    return obj
