# conduit/supervisor/services/kb.py
from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from conduit.core.exceptions import NotFoundError, ValidationError
from conduit.supervisor.dal import kb as dal


async def list_entries(s, status=None):
    return await dal.list_entries(s, status=status)


async def create_entry(s: AsyncSession, *, topic, content, actor):
    if not content.strip():
        raise ValidationError("content required")
    obj = await dal.insert(s, topic=topic, content=content)
    await s.flush()
    return obj


async def update_entry(s: AsyncSession, kid: uuid.UUID, *, actor, **fields):
    obj = await dal.get(s, kid)
    if obj is None:
        raise NotFoundError("kb entry not found")
    if "content" in fields and fields["content"] is not None \
            and not fields["content"].strip():
        raise ValidationError("content required")
    if "status" in fields and fields["status"] not in (None, "active",
                                                        "disabled"):
        raise ValidationError("invalid status")
    await dal.update(s, obj, **fields)
    await s.flush()
    return obj
