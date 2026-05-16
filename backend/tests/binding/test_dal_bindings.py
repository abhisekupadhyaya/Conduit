# tests/binding/test_dal_bindings.py
from datetime import datetime, timedelta, timezone
from conduit.supervisor.dal import sections as sdal, rooms as rdal, stays as stdal
from conduit.public.dal import bindings as dal


async def test_binding_read(db, seeded_property, make_account):
    g = await make_account("guest", "g-bind-1")
    assert await dal.get_active_binding_for_guest(db, g.id) is None
    sec = await sdal.insert_section(db, seeded_property.id, "North")
    await db.flush()
    r = await rdal.insert_room(db, sec.id, "304")
    await db.flush()
    n = datetime.now(timezone.utc)
    await stdal.insert_stay(db, g.id, r.id, n, n + timedelta(days=1))
    await db.flush()
    trio = await dal.get_active_binding_for_guest(db, g.id)
    assert trio is not None
    stay, room, section = trio
    assert room.label == "304" and section.label == "North"
