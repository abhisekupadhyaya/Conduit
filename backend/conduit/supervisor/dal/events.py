# conduit/supervisor/dal/events.py
from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from conduit.shared.models.event import (
    Event,
    EventGuestRelocated,
    EventStayCreated,
    EventStayEnded,
)


async def insert_event(
    s: AsyncSession, *, type: str, actor_account_id: uuid.UUID | None,
) -> Event:
    e = Event(type=type, actor_account_id=actor_account_id)
    s.add(e)
    return e


async def insert_stay_created(
    s: AsyncSession, event_id: uuid.UUID, stay_id: uuid.UUID
) -> None:
    s.add(EventStayCreated(event_id=event_id, stay_id=stay_id))


async def insert_stay_ended(
    s: AsyncSession, event_id: uuid.UUID, stay_id: uuid.UUID
) -> None:
    s.add(EventStayEnded(event_id=event_id, stay_id=stay_id))


async def insert_guest_relocated(
    s: AsyncSession, event_id: uuid.UUID, stay_id: uuid.UUID,
    from_room_id: uuid.UUID, to_room_id: uuid.UUID,
) -> None:
    s.add(EventGuestRelocated(
        event_id=event_id, stay_id=stay_id,
        from_room_id=from_room_id, to_room_id=to_room_id))
