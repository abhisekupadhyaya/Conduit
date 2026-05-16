import datetime as dt
import uuid

import sqlalchemy as sa

from conduit.shared.domain import lifecycle
from conduit.shared.events import writer
from conduit.shared.models import (Account, ChildSubRequest, Event,
                                   EventChildAnswered, EventChildTriaged,
                                   EventRequestCreated, NoDispatchResolution,
                                   Property, Request, Room, Section, Stay)


async def test_transition_sets_state_and_appends_event(db, make_account):
    # The merged harness seeds no Account/Stay, so build the real FK-chain
    # precondition rows inline (same pattern as tests/spine/test_migration.py).
    await make_account("guest", f"g-{uuid.uuid4().hex[:8]}")
    acc = (await db.execute(sa.select(Account).limit(1))).scalars().first()
    assert acc is not None
    p = Property(name="T")
    db.add(p)
    await db.flush()
    s = Section(property_id=p.id, label="S")
    db.add(s)
    await db.flush()
    room = Room(section_id=s.id, label="R")
    db.add(room)
    await db.flush()
    now = dt.datetime.now(dt.timezone.utc)
    stay = Stay(guest_account_id=acc.id, room_id=room.id,
                check_in=now, check_out=now + dt.timedelta(days=1))
    db.add(stay)
    await db.flush()
    r = Request(guest_account_id=acc.id, stay_id=stay.id, raw_text="x")
    db.add(r)
    await db.flush()
    c = ChildSubRequest(request_id=r.id, text="x", outcome="no_dispatch",
                        state="intake")
    db.add(c)
    await db.flush()
    await lifecycle.transition(db, c, "triaged", actor_account_id=None)
    await db.flush()
    assert c.state == "triaged"
    ev = (await db.execute(sa.select(Event)
          .where(Event.type == "child_triaged"))).scalars().all()
    assert len(ev) == 1
    det = (await db.execute(sa.select(EventChildTriaged))).scalars().all()
    assert len(det) == 1 and det[0].child_id == c.id


async def test_request_created_event(db, make_account):
    # Build the real FK-chain precondition rows inline (same pattern as above).
    await make_account("guest", f"g-{uuid.uuid4().hex[:8]}")
    acc = (await db.execute(sa.select(Account).limit(1))).scalars().first()
    assert acc is not None
    p = Property(name="T")
    db.add(p)
    await db.flush()
    s = Section(property_id=p.id, label="S")
    db.add(s)
    await db.flush()
    room = Room(section_id=s.id, label="R")
    db.add(room)
    await db.flush()
    now = dt.datetime.now(dt.timezone.utc)
    stay = Stay(guest_account_id=acc.id, room_id=room.id,
                check_in=now, check_out=now + dt.timedelta(days=1))
    db.add(stay)
    await db.flush()
    req = Request(guest_account_id=acc.id, stay_id=stay.id, raw_text="x")
    db.add(req)
    await db.flush()
    await writer.emit_request_created(db, req.id, None)
    await db.flush()
    ev = (await db.execute(sa.select(Event)
          .where(Event.type == "request_created"))).scalars().all()
    assert len(ev) == 1
    det = (await db.execute(sa.select(EventRequestCreated))).scalars().all()
    assert len(det) == 1 and det[0].request_id == req.id


async def test_answered_transition_with_resolution(db, make_account):
    # Build the real FK-chain precondition rows inline (same pattern as above).
    await make_account("guest", f"g-{uuid.uuid4().hex[:8]}")
    acc = (await db.execute(sa.select(Account).limit(1))).scalars().first()
    assert acc is not None
    p = Property(name="T")
    db.add(p)
    await db.flush()
    s = Section(property_id=p.id, label="S")
    db.add(s)
    await db.flush()
    room = Room(section_id=s.id, label="R")
    db.add(room)
    await db.flush()
    now = dt.datetime.now(dt.timezone.utc)
    stay = Stay(guest_account_id=acc.id, room_id=room.id,
                check_in=now, check_out=now + dt.timedelta(days=1))
    db.add(stay)
    await db.flush()
    r = Request(guest_account_id=acc.id, stay_id=stay.id, raw_text="x")
    db.add(r)
    await db.flush()
    c = ChildSubRequest(request_id=r.id, text="x", outcome="no_dispatch",
                        state="intake")
    db.add(c)
    await db.flush()
    await lifecycle.transition(db, c, "triaged", actor_account_id=None)
    await db.flush()
    assert c.state == "triaged"
    res = NoDispatchResolution(child_id=c.id, mode="grounded_answer",
                               answer_text="x")
    db.add(res)
    await db.flush()
    await lifecycle.transition(db, c, "answered", actor_account_id=None,
                               resolution_child_id=c.id)
    await db.flush()
    assert c.state == "answered"
    ev = (await db.execute(sa.select(Event)
          .where(Event.type == "child_answered"))).scalars().all()
    assert len(ev) == 1
    det = (await db.execute(sa.select(EventChildAnswered))).scalars().all()
    assert (len(det) == 1 and det[0].child_id == c.id
            and det[0].resolution_child_id == c.id)
