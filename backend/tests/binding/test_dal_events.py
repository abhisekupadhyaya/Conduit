# tests/binding/test_dal_events.py
from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from conduit.supervisor.dal import (
    events as dal, rooms as rdal, sections as sdal, stays as stdal,
)
from conduit.shared.models.event import Event, EventGuestRelocated


async def test_events_dal(db, seeded_property, make_account):
    g = await make_account("guest", "g-evt-1")
    sec = await sdal.insert_section(db, seeded_property.id, "N")
    await db.flush()
    r1 = await rdal.insert_room(db, sec.id, "304")
    r2 = await rdal.insert_room(db, sec.id, "511")
    await db.flush()
    n = datetime.now(timezone.utc)
    st = await stdal.insert_stay(db, g.id, r1.id, n, n + timedelta(days=1))
    await db.flush()

    e = await dal.insert_event(db, type="stay_created", actor_account_id=None)
    await db.flush()
    await dal.insert_stay_created(db, e.id, st.id)
    assert (await db.get(Event, e.id)).type == "stay_created"
    e2 = await dal.insert_event(db, type="guest_relocated",
                                actor_account_id=None)
    await db.flush()
    await dal.insert_guest_relocated(db, e2.id, st.id, r1.id, r2.id)
    row = (await db.execute(select(EventGuestRelocated))).scalars().one()
    assert row.from_room_id == r1.id and row.to_room_id == r2.id
