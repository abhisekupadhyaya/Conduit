import datetime as dt
import uuid

import sqlalchemy as sa

from conduit.guest.dal import bindings, children as cdal, requests as rdal
from conduit.shared.models import Account, Property, Room, Section, Stay


async def _chain(db, make_account):
    """Build the real FK precondition chain (merged harness seeds none).

    All ``make_account`` calls (which ``commit``) happen FIRST, before any
    Stay row is flushed — so the conftest teardown (rollback then
    ``DELETE FROM account``) is not blocked by a committed Stay FK. Returns
    the active-stay account, a no-stay account, section, room, stay.
    """
    acc = await make_account("guest", f"g-{uuid.uuid4().hex[:8]}")
    other = await make_account("guest", f"g-{uuid.uuid4().hex[:8]}")
    assert acc is not None
    p = Property(name="T")
    db.add(p)
    await db.flush()
    sec = Section(property_id=p.id, label="S")
    db.add(sec)
    await db.flush()
    room = Room(section_id=sec.id, label="R")
    db.add(room)
    await db.flush()
    now = dt.datetime.now(dt.timezone.utc)
    stay = Stay(guest_account_id=acc.id, room_id=room.id,
                check_in=now, check_out=now + dt.timedelta(days=1),
                status="active")
    db.add(stay)
    await db.flush()
    return acc, other, sec, room, stay


async def test_binding_and_request_insert(db, make_account):
    acc, other, sec, room, stay = await _chain(db, make_account)

    # Binding resolution for a guest WITH an active stay → (Stay,Room,Section).
    trio = await bindings.get_active_binding_for_guest(db, acc.id)
    assert trio is not None
    got_stay, got_room, got_section = trio
    assert got_stay.id == stay.id
    assert got_room.id == room.id
    assert got_section.id == sec.id

    # An account with no active stay → None.
    assert await bindings.get_active_binding_for_guest(db, other.id) is None

    # An ended stay is not "active" → None.
    stay.status = "ended"
    db.add(stay)
    await db.flush()
    assert await bindings.get_active_binding_for_guest(db, acc.id) is None
    stay.status = "active"
    db.add(stay)
    await db.flush()

    # Request insert/get round-trip.
    r = await rdal.insert_request(db, guest_account_id=acc.id,
                                  stay_id=stay.id, raw_text="hi")
    await db.flush()
    got = await rdal.get_request(db, r.id)
    assert got is not None
    assert got.raw_text == "hi"
    assert got.channel == "text"

    lst = await rdal.list_requests_for_guest(db, acc.id)
    assert [x.id for x in lst] == [r.id]

    # Children DAL: insert + list-for-request + list-for-guest.
    child = await cdal.insert_child(db, request_id=r.id, text="c",
                                    outcome="no_dispatch", state="intake")
    await db.flush()
    fetched = await cdal.get_child(db, child.id)
    assert fetched is not None and fetched.text == "c"
    assert [x.id for x in await cdal.list_children_for_request(db, r.id)] \
        == [child.id]
    assert [x.id for x in await cdal.list_children_for_guest(db, acc.id)] \
        == [child.id]
