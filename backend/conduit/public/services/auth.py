"""Public auth — business logic only. Identical error for every failed
login (no user enumeration). status is re-checked, never trusted from a
token."""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from conduit.core.exceptions import AuthError, ConduitError
from conduit.core.security import hash_password, verify_password
from conduit.public.dal import accounts as dal
from conduit.shared.models import Account

_BAD = "invalid username or password"


async def authenticate(s: AsyncSession, username: str, password: str) -> Account:
    acc = await dal.get_by_username(s, username)
    if acc is None or not verify_password(password, acc.secret_hash):
        raise AuthError(_BAD)
    if acc.status != "active":
        raise AuthError(_BAD)
    return acc


async def current_account(s: AsyncSession, account_id: str) -> Account:
    acc = await dal.get_by_id(s, account_id)
    if acc is None or acc.status != "active":
        raise AuthError("not authenticated")
    return acc


async def update_self(s: AsyncSession, acc: Account, *, status_change=None,
                      display_name: str | None, current_password: str | None,
                      new_password: str | None) -> Account:
    if display_name is not None:
        if not display_name.strip():
            raise ConduitError("display name required")
        acc.display_name = display_name
    if new_password is not None:
        if not verify_password(current_password or "", acc.secret_hash):
            raise AuthError("current password is incorrect")
        if len(new_password) < 6:
            raise ConduitError("password too short")
        acc.secret_hash = hash_password(new_password)
    s.add(acc)
    await s.flush()
    return acc
