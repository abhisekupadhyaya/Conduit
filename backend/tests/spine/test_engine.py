import datetime as dt, uuid, pytest
from conduit.shared.engine import timers
from conduit.shared.models import Timer
from sqlalchemy import select

@pytest.mark.asyncio
async def test_arm_writes_pending_timer(db, make_child):
    child = await make_child(db)
    await timers.arm(db, "child_id", child.id, timers.TimerType.ACCEPT_WINDOW,
                     fire_at=dt.datetime.now(dt.UTC) + dt.timedelta(minutes=15))
    await db.flush()
    rows = (await db.execute(select(Timer).where(Timer.child_id == child.id))).scalars().all()
    assert len(rows) == 1 and rows[0].state == "pending" and rows[0].type == "accept_window"

@pytest.mark.asyncio
async def test_cancel_for_marks_cancelled(db, make_child):
    child = await make_child(db)
    await timers.arm(db, "child_id", child.id, timers.TimerType.FULFILMENT_SLA,
                     fire_at=dt.datetime.now(dt.UTC))
    await db.flush()
    await timers.cancel_for(db, "child_id", child.id)
    await db.flush()
    rows = (await db.execute(select(Timer).where(Timer.child_id == child.id))).scalars().all()
    assert all(r.state == "cancelled" for r in rows)
