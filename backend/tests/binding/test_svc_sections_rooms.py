# tests/binding/test_svc_sections_rooms.py
import uuid
import pytest
from conduit.supervisor.services import sections as ssvc, rooms as rsvc
from conduit.core.exceptions import NotFoundError, ConflictError, ValidationError


async def test_sections(db, seeded_property):
    s = await ssvc.create_section(db, seeded_property.id, "North", actor=None)
    await db.flush()
    assert any(sec.id == s.id and c == 0
               for sec, c in await ssvc.list_sections(db))
    with pytest.raises(ConflictError):
        await ssvc.create_section(db, seeded_property.id, "north", actor=None)
    with pytest.raises(NotFoundError):
        await ssvc.rename_section(db, uuid.uuid4(), "X", actor=None)


async def test_rooms(db, seeded_property):
    sec = await ssvc.create_section(db, seeded_property.id, "N", actor=None)
    await db.flush()
    r = await rsvc.create_room(db, "304", sec.id, actor=None)
    await db.flush()
    assert r.id in [x.id for x in await rsvc.list_rooms(db, sec.id)]
    with pytest.raises(ValidationError):
        await rsvc.create_room(db, "9", uuid.uuid4(), actor=None)
    with pytest.raises(ConflictError):
        await rsvc.create_room(db, "304", sec.id, actor=None)
    with pytest.raises(NotFoundError):
        await rsvc.update_room(db, uuid.uuid4(), label="X", actor=None)
    other = await ssvc.create_section(db, seeded_property.id, "S", actor=None)
    await db.flush()
    await rsvc.update_room(db, r.id, section_id=other.id, actor=None)
    assert (await rsvc.list_rooms(db, other.id))[0].id == r.id
