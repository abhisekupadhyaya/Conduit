"""Account persistence. Owned by the public slice; imported by supervisor
services. Pure SQL — no hashing, no rules (code-structure note)."""
from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from conduit.shared.models import Account


async def get_by_username(s: AsyncSession, username: str) -> Account | None:
    res = await s.execute(
        select(Account).where(func.lower(Account.username) == username.lower())
    )
    return res.scalar_one_or_none()


async def get_by_id(s: AsyncSession, account_id: uuid.UUID | str) -> Account | None:
    return await s.get(Account, account_id)


async def list_accounts(
    s: AsyncSession, role: str | None = None, status: str | None = None
) -> list[Account]:
    q = select(Account)
    if role:
        q = q.where(Account.role == role)
    if status:
        q = q.where(Account.status == status)
    q = q.order_by(Account.created_at, Account.username)
    return list((await s.execute(q)).scalars().all())


async def insert_account(
    s: AsyncSession, *, role: str, username: str, secret_hash: str,
    display_name: str, status: str = "active",
) -> Account:
    a = Account(role=role, username=username, secret_hash=secret_hash,
                display_name=display_name, status=status)
    s.add(a)
    return a


async def update_account(s: AsyncSession, account: Account, **fields) -> Account:
    for k, v in fields.items():
        setattr(account, k, v)
    s.add(account)
    return account


async def count_active_by_role(s: AsyncSession, role: str) -> int:
    res = await s.execute(
        select(func.count()).select_from(Account)
        .where(Account.role == role, Account.status == "active")
    )
    return int(res.scalar_one())
