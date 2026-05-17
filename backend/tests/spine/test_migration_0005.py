import pytest
from sqlalchemy import inspect
from conduit.shared.models import SLAPreset, EscalationLadder
from conduit.shared.models import WorkOrder, Timer, Escalation
from conduit.shared.models import (Recommendation, RecReassign, RecRelocate,
    RecExtendSla, RecApprove, RecDeny, RecBroadcast)
from conduit.shared.models import Glitch, CrossDeptNotification
from conduit.shared.models import ChildSubRequest, IssueCode


def test_sla_preset_columns():
    cols = {c.name for c in inspect(SLAPreset).columns}
    assert cols == {"id", "property_id", "tier", "accept_window_seconds",
                    "fulfilment_sla_seconds", "supervisor_sla_seconds",
                    "status", "created_at", "updated_at"}


def test_escalation_ladder_columns():
    cols = {c.name for c in inspect(EscalationLadder).columns}
    assert cols == {"id", "property_id", "duty_manager_account_id",
                    "n_cycle_bound", "status", "created_at", "updated_at"}


def test_work_order_columns():
    cols = {c.name for c in inspect(WorkOrder).columns}
    assert cols == {"id", "child_id", "kind", "routing_model",
                    "assigned_servicer_id", "accountable_owner_id",
                    "section_id", "priority_tier", "queue_position", "state",
                    "completion_notes", "created_at", "updated_at"}


def test_timer_columns():
    cols = {c.name for c in inspect(Timer).columns}
    assert cols == {"id", "type", "child_id", "work_order_id", "escalation_id",
                    "fire_at", "state", "cycle", "created_at"}


def test_escalation_columns():
    cols = {c.name for c in inspect(Escalation).columns}
    assert cols == {"id", "child_id", "trigger", "state", "cycle_count",
                    "raised_by_account_id", "resolved_by_account_id",
                    "created_at", "resolved_at"}


def test_recommendation_family():
    base = {c.name for c in inspect(Recommendation).columns}
    assert base == {"escalation_id","action","rationale_text","created_at"}
    assert {c.name for c in inspect(RecReassign).columns} == {"recommendation_escalation_id","target_account_id"}
    assert {c.name for c in inspect(RecRelocate).columns} == {"recommendation_escalation_id","target_room_id"}
    assert {c.name for c in inspect(RecExtendSla).columns} == {"recommendation_escalation_id","extend_seconds"}
    for m in (RecApprove, RecDeny, RecBroadcast):
        assert {c.name for c in inspect(m).columns} == {"recommendation_escalation_id"}


def test_glitch_columns():
    assert {c.name for c in inspect(Glitch).columns} == {"id","child_id","state",
        "opened_from","recovery_owed","recovery_cost","created_at","closed_at"}


def test_cross_dept_columns():
    assert {c.name for c in inspect(CrossDeptNotification).columns} == {"id",
        "source_work_order_id","target_department","child_id","reason","state","created_at"}


def test_child_additive_columns():
    cols = {c.name for c in inspect(ChildSubRequest).columns}
    assert {"priority_tier","closure","revised_eta","predecessor_child_id"} <= cols


def test_child_state_check_widened():
    ck = next(c for c in ChildSubRequest.__table__.constraints
              if getattr(c, "name", "") == "ck_child_state")
    txt = str(ck.sqltext)
    for s in ("routing","pushed","broadcast","accepted","in_progress",
              "done_pending_confirm","cancelled"):
        assert s in txt


def test_issue_code_sla_fk():
    assert "sla_preset_id" in {c.name for c in inspect(IssueCode).columns}


from conduit.shared.models import Event

def test_event_type_extended():
    ck = next(c for c in Event.__table__.constraints
              if getattr(c, "name", "") == "ck_event_type")
    txt = str(ck.sqltext)
    for t in ("work_order_created","work_order_completed","child_routed",
              "child_closed_confirmed","escalation_opened","escalation_resolved",
              "recommendation_created","glitch_opened","glitch_closed",
              "cross_dept_notified","timer_fired","sla_preset_created",
              "escalation_ladder_created"):
        assert t in txt


# --------------------------------------------------------------------------
# Step 1 (A7): physical-invariant tests against the live 0005 schema.
# These exercise the *migrated database* (not just ORM metadata): the
# tests/spine ``db`` fixture is a savepoint-isolated AsyncSession bound to a
# DB built by ``alembic upgrade head`` (root conftest ``_create_test_db``),
# so a clean 0005 round-trip is a precondition for them to pass.
# --------------------------------------------------------------------------
import datetime as dt
import importlib
import uuid

import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError


async def _child(db, make_account):
    """Build the real FK-chain precondition rows (mirrors the proven inline
    arrange in test_migration.py / conftest.seeded_guest_with_stay) and return
    a flushed ChildSubRequest plus its Property id."""
    from conduit.shared.models import (Account, ChildSubRequest, Property,
                                       Request, Room, Section, Stay)
    await make_account("guest", f"g-{uuid.uuid4().hex[:8]}")
    acc = (await db.execute(sa.select(Account).limit(1))).scalars().first()
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
                check_in=now, check_out=now + dt.timedelta(days=1))
    db.add(stay)
    await db.flush()
    r = Request(guest_account_id=acc.id, stay_id=stay.id, raw_text="x")
    db.add(r)
    await db.flush()
    c = ChildSubRequest(request_id=r.id, text="x", outcome="auto",
                        state="triaged")
    db.add(c)
    await db.flush()
    return c, p.id


@pytest.mark.asyncio
async def test_migration_round_trip(db):
    """All 9 core spine tables physically exist in the migrated DB."""
    names = set(
        await db.run_sync(lambda s: sa.inspect(s.bind).get_table_names())
    )
    for t in ("work_order", "timer", "escalation", "recommendation",
              "rec_reassign", "glitch", "cross_dept_notification",
              "sla_preset", "escalation_ladder"):
        assert t in names


@pytest.mark.asyncio
async def test_timer_zero_subject_check(db):
    """ck_timer_one_subject rejects a Timer with ZERO subject FKs set."""
    from conduit.shared.models import Timer
    bad = Timer(type="accept_window", fire_at=dt.datetime.now(dt.UTC))
    db.add(bad)
    with pytest.raises(IntegrityError):
        await db.flush()


@pytest.mark.asyncio
async def test_timer_two_subject_check(db, make_account):
    """ck_timer_one_subject rejects a Timer with TWO subject FKs set
    (the one-subject CHECK rejects 0 and >=2 — only exactly 1 is valid)."""
    from conduit.shared.models import Timer, WorkOrder
    c, _ = await _child(db, make_account)
    wo = WorkOrder(child_id=c.id, kind="dispatch",
                   routing_model="section_pooled", priority_tier="P2")
    db.add(wo)
    await db.flush()
    bad = Timer(type="accept_window", fire_at=dt.datetime.now(dt.UTC),
                child_id=c.id, work_order_id=wo.id)  # two subjects
    db.add(bad)
    with pytest.raises(IntegrityError):
        await db.flush()


@pytest.mark.asyncio
async def test_timer_one_subject_ok(db, make_account):
    """Positive: exactly ONE subject FK set is accepted."""
    from conduit.shared.models import Timer
    c, _ = await _child(db, make_account)
    ok = Timer(type="accept_window", fire_at=dt.datetime.now(dt.UTC),
               child_id=c.id)
    db.add(ok)
    await db.flush()  # must not raise
    assert ok.id is not None


@pytest.mark.asyncio
async def test_work_order_child_unique(db, make_account):
    """A 2nd work_order for the same child_id is rejected (UNIQUE)."""
    from conduit.shared.models import WorkOrder
    c, _ = await _child(db, make_account)
    db.add(WorkOrder(child_id=c.id, kind="dispatch",
                     routing_model="section_pooled", priority_tier="P1"))
    await db.flush()
    db.add(WorkOrder(child_id=c.id, kind="dispatch",
                     routing_model="section_pooled", priority_tier="P1"))
    with pytest.raises(IntegrityError):
        await db.flush()


@pytest.mark.asyncio
async def test_glitch_child_unique(db, make_account):
    """A 2nd glitch for the same child_id is rejected (UNIQUE)."""
    from conduit.shared.models import Glitch
    c, _ = await _child(db, make_account)
    db.add(Glitch(child_id=c.id, opened_from="problem_report"))
    await db.flush()
    db.add(Glitch(child_id=c.id, opened_from="dispute"))
    with pytest.raises(IntegrityError):
        await db.flush()


@pytest.mark.asyncio
async def test_sla_preset_partial_unique(db, make_account):
    """Only ONE ACTIVE sla_preset per (property_id, tier); a 2nd ACTIVE is
    rejected by the partial-unique index uq_sla_active_tier, BUT a 2nd with
    status='disabled' is ALLOWED (partial index excludes non-active rows)."""
    from conduit.shared.models import SLAPreset
    _, pid = await _child(db, make_account)

    def _preset(status="active"):
        return SLAPreset(property_id=pid, tier="P2",
                         accept_window_seconds=60, fulfilment_sla_seconds=600,
                         supervisor_sla_seconds=1200, status=status)

    db.add(_preset())
    await db.flush()
    # disabled duplicate for the SAME (property_id, tier): allowed.
    db.add(_preset(status="disabled"))
    await db.flush()  # must not raise
    # 2nd ACTIVE duplicate: rejected.
    db.add(_preset())
    with pytest.raises(IntegrityError):
        await db.flush()


@pytest.mark.asyncio
async def test_escalation_ladder_partial_unique(db, make_account):
    """Only ONE ACTIVE escalation_ladder per property; a 2nd ACTIVE is
    rejected by uq_ladder_active_property; a disabled one is ALLOWED."""
    from conduit.shared.models import Account, EscalationLadder
    _, pid = await _child(db, make_account)
    acc = (await db.execute(sa.select(Account).limit(1))).scalars().first()

    def _ladder(status="active"):
        return EscalationLadder(property_id=pid,
                                duty_manager_account_id=acc.id,
                                n_cycle_bound=3, status=status)

    db.add(_ladder())
    await db.flush()
    db.add(_ladder(status="disabled"))  # disabled duplicate: allowed
    await db.flush()  # must not raise
    db.add(_ladder())  # 2nd ACTIVE: rejected
    with pytest.raises(IntegrityError):
        await db.flush()


def test_down_revision_is_0004_staffing():
    """0005 chains directly off 0004_staffing."""
    m = importlib.import_module("migrations.versions.0005_dispatch_spine")
    assert m.down_revision == "0004_staffing"
    assert m.revision == "0005_dispatch"
