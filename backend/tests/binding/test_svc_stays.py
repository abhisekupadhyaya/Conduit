# tests/binding/test_svc_stays.py
import uuid
from datetime import datetime, timedelta, timezone
import pytest
from sqlalchemy import func, select
from conduit.supervisor.services import sections as ssvc, rooms as rsvc, stays as svc
from conduit.core.exceptions import NotFoundError, ConflictError, ValidationError
from conduit.shared.models.event import (
    Event, EventStayCreated, EventStayEnded, EventGuestRelocated,
)


async def _rooms(db, seeded_property):
    s = await ssvc.create_section(db, seeded_property.id, "N", actor=None)
    await db.flush()
    r1 = await rsvc.create_room(db, "304", s.id, actor=None)
    r2 = await rsvc.create_room(db, "511", s.id, actor=None)
    await db.flush()
    return r1, r2


def _win():
    n = datetime.now(timezone.utc)
    return n, n + timedelta(days=2)


async def test_create_emits_event(db, seeded_property, make_account):
    g = await make_account("guest", "g-s1")
    r1, _ = await _rooms(db, seeded_property)
    ci, co = _win()
    st = await svc.create_stay(db, g.id, r1.id, ci, co, actor=None)
    await db.flush()
    assert st.status == "active"
    assert (await db.execute(
        select(func.count()).select_from(EventStayCreated))).scalar_one() == 1
    assert (await db.execute(select(Event))).scalars().one().type \
        == "stay_created"


async def test_create_guards(db, seeded_property, make_account):
    r1, _ = await _rooms(db, seeded_property)
    ci, co = _win()
    sup = await make_account("supervisor", "s-bad")
    with pytest.raises(ValidationError):
        await svc.create_stay(db, sup.id, r1.id, ci, co, actor=None)
    g = await make_account("guest", "g-s2")
    with pytest.raises(ValidationError):
        await svc.create_stay(db, g.id, uuid.uuid4(), ci, co, actor=None)
    await svc.create_stay(db, g.id, r1.id, ci, co, actor=None)
    await db.flush()
    with pytest.raises(ConflictError):
        await svc.create_stay(db, g.id, r1.id, ci, co, actor=None)


async def test_update_benign_no_event(db, seeded_property, make_account):
    g = await make_account("guest", "g-s3")
    r1, _ = await _rooms(db, seeded_property)
    ci, co = _win()
    st = await svc.create_stay(db, g.id, r1.id, ci, co, actor=None)
    await db.flush()
    before = (await db.execute(
        select(func.count()).select_from(Event))).scalar_one()
    await svc.update_stay(db, st.id, check_out=co + timedelta(days=1),
                          actor=None)
    after = (await db.execute(
        select(func.count()).select_from(Event))).scalar_one()
    assert before == after
    with pytest.raises(NotFoundError):
        await svc.update_stay(db, uuid.uuid4(), actor=None)


async def test_relocate(db, seeded_property, make_account):
    g = await make_account("guest", "g-s4")
    r1, r2 = await _rooms(db, seeded_property)
    ci, co = _win()
    st = await svc.create_stay(db, g.id, r1.id, ci, co, actor=None)
    await db.flush()
    with pytest.raises(NotFoundError):
        await svc.relocate_stay(db, uuid.uuid4(), r2.id, actor=None)
    with pytest.raises(ConflictError):
        await svc.relocate_stay(db, st.id, r1.id, actor=None)
    with pytest.raises(ValidationError):
        await svc.relocate_stay(db, st.id, uuid.uuid4(), actor=None)
    await svc.relocate_stay(db, st.id, r2.id, actor=None)
    await db.flush()
    rel = (await db.execute(
        select(EventGuestRelocated))).scalars().one()
    assert rel.from_room_id == r1.id and rel.to_room_id == r2.id


async def test_checkout_then_recheckin(db, seeded_property, make_account):
    g = await make_account("guest", "g-s5")
    r1, r2 = await _rooms(db, seeded_property)
    ci, co = _win()
    st = await svc.create_stay(db, g.id, r1.id, ci, co, actor=None)
    await db.flush()
    await svc.checkout_stay(db, st.id, actor=None)
    await db.flush()
    assert (await db.execute(
        select(func.count()).select_from(EventStayEnded))).scalar_one() == 1
    with pytest.raises(ConflictError):
        await svc.relocate_stay(db, st.id, r2.id, actor=None)
    await svc.create_stay(db, g.id, r1.id, ci, co, actor=None)  # allowed
