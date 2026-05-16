"""Supervisor account management — business logic only."""
from __future__ import annotations

import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from conduit.core.deps import Actor
from conduit.core.exceptions import ConflictError, ConduitError, NotFoundError
from conduit.core.security import hash_password
from conduit.public.dal import accounts as dal
from conduit.shared.models import Account
from conduit.shared.models.account import ROLES

_PATCHABLE = {"display_name", "status", "password"}


async def list_accounts(s: AsyncSession, role: str | None = None,
                         status: str | None = None) -> list[Account]:
    return await dal.list_accounts(s, role=role, status=status)


async def create_account(s: AsyncSession, *, role: str, username: str,
                         display_name: str, password: str) -> Account:
    if role not in ROLES:
        raise ConduitError(f"invalid role '{role}'")
    if not password or len(password) < 6:
        raise ConduitError("password too short")
    if await dal.get_by_username(s, username) is not None:
        raise ConflictError("username already exists")
    a = await dal.insert_account(
        s, role=role, username=username,
        secret_hash=hash_password(password), display_name=display_name)
    try:
        await s.flush()
    except IntegrityError as e:  # race on the unique index
        raise ConflictError("username already exists") from e
    return a


async def update_account(s: AsyncSession, actor: Actor,
                          account_id: uuid.UUID | str, patch: dict) -> Account:
    unknown = set(patch) - _PATCHABLE
    if unknown:
        raise ConduitError(f"unsupported fields: {sorted(unknown)}")
    acc = await dal.get_by_id(s, account_id)
    if acc is None:
        raise NotFoundError("account not found")

    if patch.get("status") == "disabled":
        if str(acc.id) == str(actor.id):
            raise ConflictError("cannot disable your own account")
        if acc.role == "supervisor" and acc.status == "active":
            if await dal.count_active_by_role(s, "supervisor") <= 1:
                raise ConflictError("cannot disable the last active supervisor")
    if "role" in patch:  # defense — role is not patchable, but guard anyway
        raise ConduitError("role is immutable")

    fields: dict = {}
    if "display_name" in patch:
        fields["display_name"] = patch["display_name"]
    if "status" in patch:
        fields["status"] = patch["status"]
    if patch.get("password"):
        fields["secret_hash"] = hash_password(patch["password"])
    await dal.update_account(s, acc, **fields)
    await s.flush()
    return acc
