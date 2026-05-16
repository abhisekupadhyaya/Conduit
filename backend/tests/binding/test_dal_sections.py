# tests/binding/test_dal_sections.py
from conduit.supervisor.dal import sections as dal


async def test_section_dal(db, seeded_property):
    s = await dal.insert_section(db, seeded_property.id, "North Wing")
    await db.flush()
    assert (await dal.get_section(db, s.id)).label == "North Wing"
    assert (await dal.get_section_by_label(
        db, seeded_property.id, "north wing")).id == s.id
    rows = await dal.list_sections_with_room_counts(db)
    assert any(sec.id == s.id and c == 0 for sec, c in rows)
    await dal.update_section(db, s, label="North")
    assert (await dal.get_section(db, s.id)).label == "North"
