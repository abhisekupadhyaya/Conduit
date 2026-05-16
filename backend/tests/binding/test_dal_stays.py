# tests/binding/test_dal_stays.py
from datetime import datetime, timedelta, timezone
from conduit.supervisor.dal import sections as sdal, rooms as rdal, stays as dal


async def test_stay_dal(db, seeded_property, make_account):
    g = await make_account("guest", "g-dal-1")
    sec = await sdal.insert_section(db, seeded_property.id, "N")
    await db.flush()
    r = await rdal.insert_room(db, sec.id, "304")
    await db.flush()
    n = datetime.now(timezone.utc)
    st = await dal.insert_stay(db, g.id, r.id, n, n + timedelta(days=2))
    await db.flush()
    assert (await dal.get_stay(db, st.id)).id == st.id
    assert (await dal.get_active_stay_for_guest(db, g.id)).id == st.id
    await dal.set_stay_room(db, st, r.id)
    await dal.set_stay_status(db, st, "ended")
    assert await dal.get_active_stay_for_guest(db, g.id) is None
    assert st.id in [x.id for x in await dal.list_stays(db, guest_id=g.id)]
