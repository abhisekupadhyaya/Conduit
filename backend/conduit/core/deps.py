"""FastAPI dependencies: DB session, current actor, coarse role gates.

RBAC is explicitly out of scope (product decision) — this is a 3-role gate
(guest / servicer / supervisor, plus the duty_manager backstop), not a
permission engine.
"""
from __future__ import annotations

from collections.abc import AsyncGenerator
from dataclasses import dataclass

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from conduit.core.config import get_settings
from conduit.core.exceptions import AuthError, ForbiddenError
from conduit.core.security import decode_token
from conduit.shared.db import get_session as _get_session


async def db_session() -> AsyncGenerator[AsyncSession, None]:
    async for s in _get_session():
        yield s


@dataclass(frozen=True)
class Actor:
    id: str
    role: str


async def current_actor(request: Request) -> Actor:
    s = get_settings()
    token = request.cookies.get(s.cookie_name)
    if not token:
        raise AuthError("not authenticated")
    payload = decode_token(token)
    return Actor(id=str(payload.get("sub")), role=str(payload.get("role")))


def require_roles(*roles: str):
    """Return a dependency that admits only the given roles."""

    async def _gate(actor: Actor = Depends(current_actor)) -> Actor:
        if actor.role not in roles:
            raise ForbiddenError(f"role '{actor.role}' not permitted here")
        return actor

    return _gate
