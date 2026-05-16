# conduit/shared/events/writer.py
from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from conduit.shared.models import (
    Event, EventRequestCreated, EventChildTriaged, EventChildAnswered,
    EventChildDeferred, EventChildParked, EventChildClosed, EventChildReopened,
)

_CHILD_DETAIL = {
    "child_triaged": EventChildTriaged,
    "child_deferred": EventChildDeferred,
    "child_parked": EventChildParked,
    "child_closed": EventChildClosed,
    "child_reopened": EventChildReopened,
}


async def emit_request_created(s: AsyncSession, request_id: uuid.UUID,
                               actor_account_id: uuid.UUID | None) -> None:
    e = Event(type="request_created", actor_account_id=actor_account_id)
    s.add(e)
    await s.flush()
    s.add(EventRequestCreated(event_id=e.id, request_id=request_id))


async def emit_child(s: AsyncSession, etype: str, child_id: uuid.UUID,
                     actor_account_id: uuid.UUID | None,
                     resolution_child_id: uuid.UUID | None = None) -> None:
    e = Event(type=etype, actor_account_id=actor_account_id)
    s.add(e)
    await s.flush()
    if etype == "child_answered":
        s.add(EventChildAnswered(event_id=e.id, child_id=child_id,
                                 resolution_child_id=resolution_child_id))
    else:
        s.add(_CHILD_DETAIL[etype](event_id=e.id, child_id=child_id))
