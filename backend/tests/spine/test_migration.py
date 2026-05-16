import datetime as dt
import importlib
import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError


def test_down_revision_chains_to_0002():
    # The merged migration idiom uses short numeric revision IDs
    # (0001/0002), so 0003 chains to "0002" — not "0002_stay_binding".
    m = importlib.import_module("migrations.versions.0003_nodispatch")
    assert m.down_revision == "0002"


async def test_partial_pk_blocks_second_resolution(db, make_account):
    # The merged harness seeds no Account/Stay (the spine conftest with
    # seed fixtures lands in a later task), so build the real FK-chain
    # precondition rows inline. The only invariant under test is
    # child_id-as-PK rejecting a 2nd resolution per child (1:1).
    from conduit.shared.models import (Account, ChildSubRequest,
                                       NoDispatchResolution, Property,
                                       Request, Room, Section, Stay)
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
                        state="triaged")
    db.add(c)
    await db.flush()
    db.add(NoDispatchResolution(child_id=c.id, mode="human_deferral"))
    await db.flush()
    db.add(NoDispatchResolution(child_id=c.id, mode="grounded_answer"))
    with pytest.raises(IntegrityError):
        await db.flush()
