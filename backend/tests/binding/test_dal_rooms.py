# tests/binding/test_dal_rooms.py
from conduit.supervisor.dal import sections as sdal, rooms as dal


async def test_room_dal(db, seeded_property):
    sec = await sdal.insert_section(db, seeded_property.id, "North")
    await db.flush()
    r = await dal.insert_room(db, sec.id, "304")
    await db.flush()
    assert (await dal.get_room(db, r.id)).label == "304"
    assert (await dal.get_room_by_label(db, "304")).id == r.id
    other = await sdal.insert_section(db, seeded_property.id, "South")
    await db.flush()
    await dal.update_room(db, r, label="305", section_id=other.id)
    got = await dal.get_room(db, r.id)
    assert got.label == "305" and got.section_id == other.id
    assert [x.id for x in await dal.list_rooms(db, other.id)] == [r.id]
