# tests/binding/conftest.py
from __future__ import annotations

import pytest_asyncio
from sqlalchemy import delete, func, select


@pytest_asyncio.fixture(autouse=True)
async def _binding_cleanup(db):
    from conduit.shared.models.event import (
        Event, EventGuestRelocated, EventStayCreated, EventStayEnded,
    )
    from conduit.shared.models.room import Room
    from conduit.shared.models.section import Section
    from conduit.shared.models.stay import Stay
    order = [EventGuestRelocated, EventStayEnded, EventStayCreated, Event,
             Stay, Room, Section]
    try:
        yield
    finally:
        await db.rollback()
        for model in order:
            await db.execute(delete(model))
        await db.commit()
        for model in (Stay, Room, Section, Event):
            n = (await db.execute(
                select(func.count()).select_from(model))).scalar_one()
            assert n == 0, f"LEAK: {model.__tablename__} = {n}"


@pytest_asyncio.fixture()
async def seeded_property(db):
    from conduit.shared.models.property import Property
    p = (await db.execute(select(Property))).scalars().first()
    if p is None:
        p = Property(name="Test Property")
        db.add(p)
        await db.flush()
    return p
