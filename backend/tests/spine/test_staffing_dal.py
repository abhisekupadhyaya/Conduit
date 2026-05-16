"""Supervisor Staff DAL + service layer bench.

Task 6 appends the physical-invariant DAL tests here; this file is created
in Task 5 with the focused ``replace_skills`` add-only + hard-replace proof
(spec §4 "Skills named exception", §11 *DAL* "replace_skills is the only
deleting method") plus the §11 *Services* layer guard/event coverage driven
through the real service entrypoints (the HTTP bench in
``test_staffing_api.py`` proves the wire contract; the service is exercised
directly here against the savepoint ``db`` — the established spine pattern,
mirroring ``test_intake_service.py``, since pytest-cov does not trace the
ASGI ``client`` app in this repo). Uses the savepoint-rollback ``db``
fixture and the ``make_account`` real-service precondition (both from
tests/spine/conftest + root conftest).
"""
from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa

from conduit.core.exceptions import (
    ConflictError,
    NotFoundError,
    ValidationError,
)
from conduit.shared.models import (
    Event,
    EventStaffProfileCreated,
    EventStaffProfileUpdated,
    EventStaffSkillsSet,
    StaffSkill,
)
from conduit.supervisor.dal import staff as dal
from conduit.supervisor.services import staff as svc


async def _skill_rows(db, account_id):
    return sorted(
        (
            await db.execute(
                sa.select(StaffSkill.skill).where(
                    StaffSkill.account_id == account_id
                )
            )
        ).scalars().all()
    )


async def test_add_profile_is_add_only_no_flush(db, make_account):
    acc = await make_account("servicer", f"srv-{uuid.uuid4().hex[:8]}")
    p = dal.add_profile(db, acc.id, "housekeeping")
    # add-only: the DAL only staged the row (pending in session.new) and
    # did NOT itself flush — services own the flush (spec §4 layering).
    assert p in db.new
    await db.flush()
    assert p not in db.new
    assert await dal.get_profile(db, acc.id) is not None


async def test_replace_skills_hard_replaces_the_row_set(db, make_account):
    acc = await make_account("servicer", f"srv-{uuid.uuid4().hex[:8]}")
    dal.add_profile(db, acc.id, "engineering")
    await db.flush()

    await dal.replace_skills(db, acc.id, ["hvac", "electrical"])
    await db.flush()
    assert await _skill_rows(db, acc.id) == ["electrical", "hvac"]

    # Replace-set: removed rows are hard-deleted, dedup + sorted.
    await dal.replace_skills(db, acc.id, ["plumbing", "plumbing", "hvac"])
    await db.flush()
    assert await _skill_rows(db, acc.id) == ["hvac", "plumbing"]
    assert "electrical" not in await _skill_rows(db, acc.id)

    # Empty set clears all rows (still no HTTP DELETE — DAL-level only).
    await dal.replace_skills(db, acc.id, [])
    await db.flush()
    assert await _skill_rows(db, acc.id) == []


async def test_list_servicer_accounts_excludes_non_servicers(
    db, make_account
):
    srv = await make_account("servicer", f"srv-{uuid.uuid4().hex[:8]}")
    guest = await make_account("guest", f"g-{uuid.uuid4().hex[:8]}")
    sup = await make_account("supervisor", f"s-{uuid.uuid4().hex[:8]}")
    ids = {a.id for a in await dal.list_servicer_accounts(db)}
    assert srv.id in ids
    assert guest.id not in ids
    assert sup.id not in ids


# --- §11 Services layer: every guard branch + one append-only event ---------


async def _count_detail(db, detail_cls, account_id):
    return len(
        (
            await db.execute(
                sa.select(detail_cls).where(
                    detail_cls.account_id == account_id
                )
            )
        ).scalars().all()
    )


async def test_service_create_profile_emits_one_event(db, make_account):
    srv = await make_account("servicer", f"srv-{uuid.uuid4().hex[:8]}")
    sup = await make_account("supervisor", f"s-{uuid.uuid4().hex[:8]}")
    p = await svc.create_profile(db, sup.id, srv.id, "housekeeping")
    await db.flush()
    assert p.staff_class == "housekeeping"
    assert await _count_detail(db, EventStaffProfileCreated, srv.id) == 1
    ev = (
        await db.execute(
            sa.select(Event).where(Event.type == "staff_profile_created")
        )
    ).scalars().all()
    assert any(str(e.actor_account_id) == str(sup.id) for e in ev)


async def test_service_create_profile_missing_account_404(db, make_account):
    sup = await make_account("supervisor", f"s-{uuid.uuid4().hex[:8]}")
    with pytest.raises(NotFoundError):
        await svc.create_profile(db, sup.id, uuid.uuid4(), "housekeeping")


async def test_service_create_profile_non_servicer_422(db, make_account):
    guest = await make_account("guest", f"g-{uuid.uuid4().hex[:8]}")
    sup = await make_account("supervisor", f"s-{uuid.uuid4().hex[:8]}")
    with pytest.raises(ValidationError):
        await svc.create_profile(db, sup.id, guest.id, "housekeeping")


async def test_service_create_profile_twice_409(db, make_account):
    srv = await make_account("servicer", f"srv-{uuid.uuid4().hex[:8]}")
    sup = await make_account("supervisor", f"s-{uuid.uuid4().hex[:8]}")
    await svc.create_profile(db, sup.id, srv.id, "engineering")
    await db.flush()
    with pytest.raises(ConflictError):
        await svc.create_profile(db, sup.id, srv.id, "housekeeping")


async def test_service_patch_profile_class_and_status(db, make_account):
    srv = await make_account("servicer", f"srv-{uuid.uuid4().hex[:8]}")
    sup = await make_account("supervisor", f"s-{uuid.uuid4().hex[:8]}")
    await svc.create_profile(db, sup.id, srv.id, "housekeeping")
    await db.flush()
    p = await svc.patch_profile(
        db, sup.id, srv.id, staff_class="runner", status="disabled"
    )
    await db.flush()
    assert p.staff_class == "runner" and p.status == "disabled"
    assert await _count_detail(db, EventStaffProfileUpdated, srv.id) == 1


async def test_service_patch_profile_noop_args(db, make_account):
    srv = await make_account("servicer", f"srv-{uuid.uuid4().hex[:8]}")
    sup = await make_account("supervisor", f"s-{uuid.uuid4().hex[:8]}")
    await svc.create_profile(db, sup.id, srv.id, "concierge")
    await db.flush()
    p = await svc.patch_profile(
        db, sup.id, srv.id, staff_class=None, status=None
    )
    await db.flush()
    assert p.staff_class == "concierge"  # unchanged, event still emitted
    assert await _count_detail(db, EventStaffProfileUpdated, srv.id) == 1


async def test_service_patch_profile_no_profile_404(db, make_account):
    srv = await make_account("servicer", f"srv-{uuid.uuid4().hex[:8]}")
    sup = await make_account("supervisor", f"s-{uuid.uuid4().hex[:8]}")
    with pytest.raises(NotFoundError):
        await svc.patch_profile(
            db, sup.id, srv.id, staff_class="runner", status=None
        )


async def test_service_set_skills_emits_one_event(db, make_account):
    srv = await make_account("servicer", f"srv-{uuid.uuid4().hex[:8]}")
    sup = await make_account("supervisor", f"s-{uuid.uuid4().hex[:8]}")
    await svc.create_profile(db, sup.id, srv.id, "engineering")
    await db.flush()
    await svc.set_skills(db, sup.id, srv.id, ["hvac", "electrical"])
    await db.flush()
    assert await dal.get_skills(db, srv.id) == ["electrical", "hvac"]
    assert await _count_detail(db, EventStaffSkillsSet, srv.id) == 1


async def test_service_set_skills_no_profile_404(db, make_account):
    srv = await make_account("servicer", f"srv-{uuid.uuid4().hex[:8]}")
    sup = await make_account("supervisor", f"s-{uuid.uuid4().hex[:8]}")
    with pytest.raises(NotFoundError):
        await svc.set_skills(db, sup.id, srv.id, ["hvac"])


async def test_service_list_and_get_staff_compose(db, make_account):
    a = await make_account("servicer", f"srv-{uuid.uuid4().hex[:8]}")
    b = await make_account("servicer", f"srv-{uuid.uuid4().hex[:8]}")
    sup = await make_account("supervisor", f"s-{uuid.uuid4().hex[:8]}")
    await svc.create_profile(db, sup.id, a.id, "housekeeping")
    await svc.set_skills(db, sup.id, a.id, ["beds"])
    await db.flush()

    rows = await svc.list_staff(db)
    by_id = {r["account_id"]: r for r in rows}
    assert by_id[a.id]["profile"] == {
        "staff_class": "housekeeping",
        "presence": "working",
        "status": "active",
    }
    assert by_id[a.id]["skills"] == ["beds"]
    assert by_id[b.id]["profile"] is None  # un-profiled is first-class
    assert by_id[b.id]["skills"] == []

    one = await svc.get_staff(db, a.id)
    assert one["display_name"] == a.display_name
    assert one["profile"]["staff_class"] == "housekeeping"

    unprof = await svc.get_staff(db, b.id)
    assert unprof["profile"] is None


async def test_service_get_staff_not_servicer_404(db, make_account):
    guest = await make_account("guest", f"g-{uuid.uuid4().hex[:8]}")
    with pytest.raises(NotFoundError):
        await svc.get_staff(db, guest.id)
    with pytest.raises(NotFoundError):
        await svc.get_staff(db, uuid.uuid4())


# ===========================================================================
# Task 6 — PHYSICAL invariants against the live schema (spec §6, §11
# *Migration* "the three physical invariants tested negative AND positive").
#
# Under the savepoint-rollback conftest the session already runs inside one
# nested SAVEPOINT; an IntegrityError poisons the *current* (sub)transaction.
# To assert an expected IntegrityError WITHOUT poisoning sibling assertions in
# the same test we open our OWN inner ``db.begin_nested()`` savepoint around
# the offending flush: on IntegrityError that inner savepoint is rolled back
# (``async with`` exits via the exception), the outer savepoint stays live,
# and the test continues / the next test is unaffected. The conftest's
# ``after_transaction_end`` listener only restarts the OUTERMOST nested
# transaction (``not transaction._parent.nested``), so a hand-rolled inner
# savepoint is left entirely to us — exactly the merged isolation contract.
# ===========================================================================
from sqlalchemy.exc import IntegrityError  # noqa: E402

from conduit.shared.models import (  # noqa: E402
    Property,
    Roster,
    RosterAssignment,
    Section,
    StaffProfile,
)


async def _expect_integrity_error(db, mk_row):
    """Add ``mk_row()`` inside a private inner savepoint and assert the flush
    raises IntegrityError; roll the inner savepoint back so the outer session
    stays usable (sibling assertions + the next test are unaffected)."""
    sp = await db.begin_nested()
    raised = False
    try:
        db.add(mk_row())
        await db.flush()
    except IntegrityError:
        raised = True
        await sp.rollback()
    if not raised:
        await sp.rollback()
    assert raised, "expected IntegrityError was not raised"


async def _seed_property_section(db):
    p = Property(name=f"P-{uuid.uuid4().hex[:8]}")
    db.add(p)
    await db.flush()
    sec = Section(property_id=p.id, label=f"S-{uuid.uuid4().hex[:6]}")
    db.add(sec)
    await db.flush()
    return p, sec


async def test_second_staff_profile_rejected(db, make_account):
    acc = await make_account("servicer", f"srv-{uuid.uuid4().hex[:8]}")
    db.add(StaffProfile(account_id=acc.id, staff_class="housekeeping"))
    await db.flush()
    # account_id-is-pk => the 1:1 physical invariant: a 2nd profile rejected.
    await _expect_integrity_error(
        db, lambda: StaffProfile(account_id=acc.id, staff_class="engineering")
    )


async def test_duplicate_staff_skill_rejected(db, make_account):
    acc = await make_account("servicer", f"srv-{uuid.uuid4().hex[:8]}")
    db.add(StaffSkill(account_id=acc.id, skill="hvac"))
    await db.flush()
    # composite pk (account_id, skill) => dup skill per account rejected.
    await _expect_integrity_error(
        db, lambda: StaffSkill(account_id=acc.id, skill="hvac")
    )


async def test_owner_without_section_rejected_by_check(db, make_account):
    acc = await make_account("servicer", f"srv-{uuid.uuid4().hex[:8]}")
    _, sec = await _seed_property_section(db)
    now = __import__("datetime").datetime(
        2026, 5, 16, 8, 0, tzinfo=__import__("datetime").timezone.utc
    )
    r = Roster(
        property_id=sec.property_id,
        shift_start=now,
        shift_end=now + __import__("datetime").timedelta(hours=8),
    )
    db.add(r)
    await db.flush()
    # DB CHECK ck_assignment_owner_needs_section (D12): owner w/o section.
    await _expect_integrity_error(
        db,
        lambda: RosterAssignment(
            roster_id=r.id,
            account_id=acc.id,
            section_id=None,
            assignment="owner",
        ),
    )


async def test_second_active_owner_rejected_disabled_and_elsewhere_ok(
    db, make_account
):
    import datetime as _dt

    a = await make_account("servicer", f"srv-{uuid.uuid4().hex[:8]}")
    b = await make_account("servicer", f"srv-{uuid.uuid4().hex[:8]}")
    p = Property(name=f"P-{uuid.uuid4().hex[:8]}")
    db.add(p)
    await db.flush()
    sec1 = Section(property_id=p.id, label="A")
    sec2 = Section(property_id=p.id, label="B")
    db.add_all([sec1, sec2])
    await db.flush()
    now = _dt.datetime(2026, 5, 16, 8, 0, tzinfo=_dt.UTC)
    r = Roster(
        property_id=p.id,
        shift_start=now,
        shift_end=now + _dt.timedelta(hours=8),
    )
    db.add(r)
    await db.flush()

    db.add(
        RosterAssignment(
            roster_id=r.id,
            account_id=a.id,
            section_id=sec1.id,
            assignment="owner",
        )
    )
    await db.flush()

    # NEGATIVE: a 2nd active owner for the SAME (roster, section) is rejected
    # by the partial-unique index uq_active_owner_per_section.
    await _expect_integrity_error(
        db,
        lambda: RosterAssignment(
            roster_id=r.id,
            account_id=b.id,
            section_id=sec1.id,
            assignment="owner",
        ),
    )

    # POSITIVE 1: a DISABLED owner duplicate for the same (roster, section)
    # IS allowed (the partial index is WHERE status='active').
    db.add(
        RosterAssignment(
            roster_id=r.id,
            account_id=b.id,
            section_id=sec1.id,
            assignment="owner",
            status="disabled",
        )
    )
    await db.flush()

    # POSITIVE 2: the SAME account as active owner of a DIFFERENT section IS
    # allowed (no per-account uniqueness — D12 in-zone backup pool is real).
    db.add(
        RosterAssignment(
            roster_id=r.id,
            account_id=a.id,
            section_id=sec2.id,
            assignment="owner",
        )
    )
    await db.flush()

    rows = (
        await db.execute(
            sa.select(RosterAssignment).where(
                RosterAssignment.roster_id == r.id
            )
        )
    ).scalars().all()
    assert len(rows) == 3


# ===========================================================================
# Task 6 — Rosters SERVICE layer: every guard branch + exactly one
# append-only event per mutation (spec §11 *Services*). Driven directly
# against the savepoint ``db`` (the established spine pattern — pytest-cov
# does not trace the ASGI ``client`` app in this repo, see this module's
# header docstring; the HTTP bench in test_staffing_api.py proves the wire
# contract, this proves the service logic + coverage).
# ===========================================================================
import datetime as _dt  # noqa: E402

from conduit.shared.models import (  # noqa: E402
    EventAssignmentCreated,
    EventAssignmentUpdated,
    EventRosterCreated,
    EventRosterUpdated,
)
from conduit.supervisor.services import rosters as rsvc  # noqa: E402


def _win(hours: int = 8):
    start = _dt.datetime(2026, 5, 16, 8, 0, tzinfo=_dt.UTC)
    return start, start + _dt.timedelta(hours=hours)


async def _count(db, detail_cls, fk_attr, fk_val):
    return len(
        (
            await db.execute(
                sa.select(detail_cls).where(
                    getattr(detail_cls, fk_attr) == fk_val
                )
            )
        ).scalars().all()
    )


async def test_svc_create_roster_emits_one_event(db, make_account):
    sup = await make_account("supervisor", f"s-{uuid.uuid4().hex[:8]}")
    p, _ = await _seed_property_section(db)
    s0, s1 = _win()
    r = await rsvc.create_roster(db, sup.id, p.id, s0, s1)
    await db.flush()
    assert r.status == "active"
    assert await _count(db, EventRosterCreated, "roster_id", r.id) == 1


async def test_svc_create_roster_bad_window_422(db, make_account):
    sup = await make_account("supervisor", f"s-{uuid.uuid4().hex[:8]}")
    p, _ = await _seed_property_section(db)
    s0, s1 = _win()
    with pytest.raises(ValidationError):
        await rsvc.create_roster(db, sup.id, p.id, s1, s0)
    with pytest.raises(ValidationError):
        await rsvc.create_roster(db, sup.id, p.id, s0, s0)


async def test_svc_get_roster_404(db):
    with pytest.raises(NotFoundError):
        await rsvc.get_roster(db, uuid.uuid4())


async def test_svc_update_roster_status_and_window(db, make_account):
    sup = await make_account("supervisor", f"s-{uuid.uuid4().hex[:8]}")
    p, _ = await _seed_property_section(db)
    s0, s1 = _win()
    r = await rsvc.create_roster(db, sup.id, p.id, s0, s1)
    await db.flush()
    upd = await rsvc.update_roster(
        db, sup.id, r.id,
        shift_start=s0 + _dt.timedelta(hours=1),
        shift_end=s1 + _dt.timedelta(hours=2),
        status="disabled",
    )
    await db.flush()
    assert upd.status == "disabled"
    assert await _count(db, EventRosterUpdated, "roster_id", r.id) == 1


async def test_svc_update_roster_404(db, make_account):
    sup = await make_account("supervisor", f"s-{uuid.uuid4().hex[:8]}")
    with pytest.raises(NotFoundError):
        await rsvc.update_roster(
            db, sup.id, uuid.uuid4(),
            shift_start=None, shift_end=None, status="disabled",
        )


async def test_svc_update_roster_bad_window_422(db, make_account):
    sup = await make_account("supervisor", f"s-{uuid.uuid4().hex[:8]}")
    p, _ = await _seed_property_section(db)
    s0, s1 = _win()
    r = await rsvc.create_roster(db, sup.id, p.id, s0, s1)
    await db.flush()
    with pytest.raises(ValidationError):
        await rsvc.update_roster(
            db, sup.id, r.id,
            shift_start=s1, shift_end=None, status=None,
        )


async def test_svc_create_assignment_owner_emits_one_event(
    db, make_account
):
    sup = await make_account("supervisor", f"s-{uuid.uuid4().hex[:8]}")
    srv = await make_account("servicer", f"srv-{uuid.uuid4().hex[:8]}")
    p, sec = await _seed_property_section(db)
    db.add(StaffProfile(account_id=srv.id, staff_class="housekeeping"))
    s0, s1 = _win()
    r = await rsvc.create_roster(db, sup.id, p.id, s0, s1)
    await db.flush()
    a = await rsvc.create_assignment(
        db, sup.id, r.id, srv.id, sec.id, "owner"
    )
    await db.flush()
    assert a.assignment == "owner"
    assert await _count(db, EventAssignmentCreated, "assignment_id", a.id) == 1


async def test_svc_create_assignment_roster_404(db, make_account):
    sup = await make_account("supervisor", f"s-{uuid.uuid4().hex[:8]}")
    srv = await make_account("servicer", f"srv-{uuid.uuid4().hex[:8]}")
    with pytest.raises(NotFoundError):
        await rsvc.create_assignment(
            db, sup.id, uuid.uuid4(), srv.id, None, "member"
        )


async def test_svc_create_assignment_non_servicer_422(db, make_account):
    sup = await make_account("supervisor", f"s-{uuid.uuid4().hex[:8]}")
    guest = await make_account("guest", f"g-{uuid.uuid4().hex[:8]}")
    p, _ = await _seed_property_section(db)
    s0, s1 = _win()
    r = await rsvc.create_roster(db, sup.id, p.id, s0, s1)
    await db.flush()
    with pytest.raises(ValidationError):
        await rsvc.create_assignment(
            db, sup.id, r.id, guest.id, None, "member"
        )
    with pytest.raises(ValidationError):  # missing account == not a servicer
        await rsvc.create_assignment(
            db, sup.id, r.id, uuid.uuid4(), None, "member"
        )


async def test_svc_create_assignment_no_active_profile_422(
    db, make_account
):
    sup = await make_account("supervisor", f"s-{uuid.uuid4().hex[:8]}")
    srv = await make_account("servicer", f"srv-{uuid.uuid4().hex[:8]}")
    p, _ = await _seed_property_section(db)
    s0, s1 = _win()
    r = await rsvc.create_roster(db, sup.id, p.id, s0, s1)
    await db.flush()
    # no profile at all
    with pytest.raises(ValidationError):
        await rsvc.create_assignment(
            db, sup.id, r.id, srv.id, None, "member"
        )
    # disabled profile
    db.add(
        StaffProfile(
            account_id=srv.id, staff_class="housekeeping", status="disabled"
        )
    )
    await db.flush()
    with pytest.raises(ValidationError):
        await rsvc.create_assignment(
            db, sup.id, r.id, srv.id, None, "member"
        )


async def test_svc_create_assignment_engineering_with_section_422(
    db, make_account
):
    sup = await make_account("supervisor", f"s-{uuid.uuid4().hex[:8]}")
    srv = await make_account("servicer", f"srv-{uuid.uuid4().hex[:8]}")
    p, sec = await _seed_property_section(db)
    db.add(StaffProfile(account_id=srv.id, staff_class="engineering"))
    s0, s1 = _win()
    r = await rsvc.create_roster(db, sup.id, p.id, s0, s1)
    await db.flush()
    with pytest.raises(ValidationError):  # D18
        await rsvc.create_assignment(
            db, sup.id, r.id, srv.id, sec.id, "member"
        )


async def test_svc_create_assignment_owner_without_section_422(
    db, make_account
):
    sup = await make_account("supervisor", f"s-{uuid.uuid4().hex[:8]}")
    srv = await make_account("servicer", f"srv-{uuid.uuid4().hex[:8]}")
    p, _ = await _seed_property_section(db)
    db.add(StaffProfile(account_id=srv.id, staff_class="housekeeping"))
    s0, s1 = _win()
    r = await rsvc.create_roster(db, sup.id, p.id, s0, s1)
    await db.flush()
    with pytest.raises(ValidationError):  # D12 (service 422 before CHECK)
        await rsvc.create_assignment(
            db, sup.id, r.id, srv.id, None, "owner"
        )
    with pytest.raises(ValidationError):  # backup too
        await rsvc.create_assignment(
            db, sup.id, r.id, srv.id, None, "backup"
        )


async def test_svc_create_assignment_dup_active_owner_409(db, make_account):
    sup = await make_account("supervisor", f"s-{uuid.uuid4().hex[:8]}")
    a = await make_account("servicer", f"srv-{uuid.uuid4().hex[:8]}")
    b = await make_account("servicer", f"srv-{uuid.uuid4().hex[:8]}")
    p, sec = await _seed_property_section(db)
    db.add(StaffProfile(account_id=a.id, staff_class="housekeeping"))
    db.add(StaffProfile(account_id=b.id, staff_class="housekeeping"))
    s0, s1 = _win()
    r = await rsvc.create_roster(db, sup.id, p.id, s0, s1)
    await db.flush()
    await rsvc.create_assignment(db, sup.id, r.id, a.id, sec.id, "owner")
    await db.flush()
    with pytest.raises(ConflictError):
        await rsvc.create_assignment(
            db, sup.id, r.id, b.id, sec.id, "owner"
        )


async def test_svc_list_assignments_404_and_compose(db, make_account):
    sup = await make_account("supervisor", f"s-{uuid.uuid4().hex[:8]}")
    srv = await make_account("servicer", f"srv-{uuid.uuid4().hex[:8]}")
    with pytest.raises(NotFoundError):
        await rsvc.list_assignments(db, uuid.uuid4())
    p, sec = await _seed_property_section(db)
    db.add(StaffProfile(account_id=srv.id, staff_class="housekeeping"))
    s0, s1 = _win()
    r = await rsvc.create_roster(db, sup.id, p.id, s0, s1)
    await db.flush()
    await rsvc.create_assignment(db, sup.id, r.id, srv.id, sec.id, "owner")
    await db.flush()
    lst = await rsvc.list_assignments(db, r.id)
    assert len(lst) == 1 and lst[0].assignment == "owner"


async def test_svc_list_rosters_status_and_active_at(db, make_account):
    sup = await make_account("supervisor", f"s-{uuid.uuid4().hex[:8]}")
    p, _ = await _seed_property_section(db)
    s0, s1 = _win()
    r = await rsvc.create_roster(db, sup.id, p.id, s0, s1)
    await db.flush()
    assert any(
        x.id == r.id for x in await rsvc.list_rosters(db, status="active")
    )
    inside = s0 + _dt.timedelta(hours=2)
    assert any(
        x.id == r.id
        for x in await rsvc.list_rosters(db, active_at=inside)
    )
    after = s1 + _dt.timedelta(hours=2)
    assert all(
        x.id != r.id
        for x in await rsvc.list_rosters(db, active_at=after)
    )


async def test_svc_update_assignment_emits_one_event(db, make_account):
    sup = await make_account("supervisor", f"s-{uuid.uuid4().hex[:8]}")
    srv = await make_account("servicer", f"srv-{uuid.uuid4().hex[:8]}")
    p, sec = await _seed_property_section(db)
    db.add(StaffProfile(account_id=srv.id, staff_class="housekeeping"))
    s0, s1 = _win()
    r = await rsvc.create_roster(db, sup.id, p.id, s0, s1)
    await db.flush()
    a = await rsvc.create_assignment(
        db, sup.id, r.id, srv.id, sec.id, "owner"
    )
    await db.flush()
    sec2_p = sec  # reuse same section ptr; switch role + disable
    upd = await rsvc.update_assignment(
        db, sup.id, r.id, a.id,
        section_id=sec2_p.id, assignment="backup", status="disabled",
    )
    await db.flush()
    assert upd.assignment == "backup" and upd.status == "disabled"
    assert await _count(db, EventAssignmentUpdated, "assignment_id", a.id) == 1


async def test_svc_update_assignment_404(db, make_account):
    sup = await make_account("supervisor", f"s-{uuid.uuid4().hex[:8]}")
    p, _ = await _seed_property_section(db)
    s0, s1 = _win()
    r = await rsvc.create_roster(db, sup.id, p.id, s0, s1)
    await db.flush()
    with pytest.raises(NotFoundError):  # roster missing
        await rsvc.update_assignment(
            db, sup.id, uuid.uuid4(), uuid.uuid4(),
            section_id=None, assignment=None, status="disabled",
        )
    with pytest.raises(NotFoundError):  # assignment missing on a real roster
        await rsvc.update_assignment(
            db, sup.id, r.id, uuid.uuid4(),
            section_id=None, assignment=None, status="disabled",
        )


# ===========================================================================
# Task 5b — supervisor-self-contained assignments-with-roster DAL helper for
# the GET /staff derived-availability extension (user-authorized scope add).
# MIRRORS servicer/dal/self.py::get_assignments (fetch assignments, batch the
# rosters by id, attach Roster as a plain .roster attribute — no ORM
# relationship, no N+1) but lives in supervisor/dal (NO conduit.servicer
# import — the inverse of Resolution E / cross-portal forbidden). Add-only,
# no flush. The pure shared.domain.availability predicate consumes the rows.
# ===========================================================================
from conduit.shared.domain import availability  # noqa: E402


async def test_dal_assignments_with_roster_no_servicer_import():
    """The supervisor staff DAL must NOT pull in conduit.servicer (forbidden
    cross-portal import) — it reimplements the fetch-and-attach itself."""
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(dal))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(n.name for n in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    assert not any(m.startswith("conduit.servicer") for m in imported), (
        f"forbidden cross-portal import: {imported}"
    )
    assert hasattr(dal, "get_assignments_with_roster")


async def test_dal_assignments_with_roster_attaches_and_batches(
    db, make_account, monkeypatch
):
    srv = await make_account("servicer", f"srv-{uuid.uuid4().hex[:8]}")
    p = Property(name=f"P-{uuid.uuid4().hex[:8]}")
    db.add(p)
    await db.flush()
    sec1 = Section(property_id=p.id, label="A")
    sec2 = Section(property_id=p.id, label="B")
    db.add_all([sec1, sec2])
    await db.flush()
    now = _dt.datetime(2026, 5, 16, 8, 0, tzinfo=_dt.UTC)
    r1 = Roster(
        property_id=p.id, shift_start=now,
        shift_end=now + _dt.timedelta(hours=8),
    )
    r2 = Roster(
        property_id=p.id, shift_start=now + _dt.timedelta(days=1),
        shift_end=now + _dt.timedelta(days=1, hours=8),
    )
    db.add_all([r1, r2])
    await db.flush()
    db.add_all([
        RosterAssignment(
            roster_id=r1.id, account_id=srv.id,
            section_id=sec1.id, assignment="owner",
        ),
        RosterAssignment(
            roster_id=r2.id, account_id=srv.id,
            section_id=sec2.id, assignment="owner",
        ),
    ])
    await db.flush()

    # Count Roster SELECTs: must be ONE batched query for both assignments
    # (no N+1) — mirrors servicer/dal/self.py::get_assignments.
    real_execute = type(db).execute
    roster_selects = 0

    async def counting_execute(self, stmt, *a, **kw):
        nonlocal roster_selects
        txt = str(stmt)
        if "FROM roster " in txt and "roster_assignment" not in txt:
            roster_selects += 1
        return await real_execute(self, stmt, *a, **kw)

    monkeypatch.setattr(type(db), "execute", counting_execute)
    rows = await dal.get_assignments_with_roster(db, srv.id)
    monkeypatch.undo()

    assert len(rows) == 2
    assert roster_selects == 1, "rosters must be fetched in ONE batched query"
    for a in rows:
        assert a.roster is not None
        assert a.roster.id == a.roster_id
    # The pure predicate consumes them unchanged: at `now` r1's window is
    # live (on shift) — proves the attach satisfies the availability contract.
    assert availability.on_shift(rows, now) is True
    assert availability.on_shift(rows, now + _dt.timedelta(days=5)) is False


async def test_dal_assignments_with_roster_empty_no_roster_query(
    db, make_account, monkeypatch
):
    """No assignments => returns [] WITHOUT issuing the roster batch query
    (matches the servicer helper's early return)."""
    srv = await make_account("servicer", f"srv-{uuid.uuid4().hex[:8]}")
    real_execute = type(db).execute
    roster_selects = 0

    async def counting_execute(self, stmt, *a, **kw):
        nonlocal roster_selects
        if "FROM roster " in str(stmt) and "roster_assignment" not in str(
            stmt
        ):
            roster_selects += 1
        return await real_execute(self, stmt, *a, **kw)

    monkeypatch.setattr(type(db), "execute", counting_execute)
    rows = await dal.get_assignments_with_roster(db, srv.id)
    monkeypatch.undo()
    assert rows == []
    assert roster_selects == 0


async def test_dal_assignments_with_roster_add_only_no_flush(
    db, make_account
):
    """Pure read: it must not leave anything pending nor flush (the merged
    DAL discipline — services own flush; reads emit nothing)."""
    srv = await make_account("servicer", f"srv-{uuid.uuid4().hex[:8]}")
    await dal.get_assignments_with_roster(db, srv.id)
    assert not db.new and not db.dirty and not db.deleted


# --- Task 5b service-layer derivation (composes the pure predicate) --------


async def test_service_staff_derives_on_shift_and_available(
    db, make_account
):
    """svc.list_staff / get_staff populate the two derived booleans using the
    SAME pure predicate + an explicit `now`; un-profiled => available False,
    on_shift profile-independent. Driven against the savepoint db (the spine
    pattern — pytest-cov does not trace the ASGI client)."""
    from conduit.core import clock

    srv = await make_account("servicer", f"srv-{uuid.uuid4().hex[:8]}")
    unp = await make_account("servicer", f"srv-{uuid.uuid4().hex[:8]}")
    sup = await make_account("supervisor", f"s-{uuid.uuid4().hex[:8]}")
    p = Property(name=f"P-{uuid.uuid4().hex[:8]}")
    db.add(p)
    await db.flush()
    sec = Section(property_id=p.id, label="A")
    db.add(sec)
    await db.flush()
    now = _dt.datetime(2026, 5, 16, 10, 0, tzinfo=_dt.UTC)
    rr = await rsvc.create_roster(
        db, sup.id, p.id,
        now - _dt.timedelta(hours=2), now + _dt.timedelta(hours=6),
    )
    await db.flush()
    await svc.create_profile(db, sup.id, srv.id, "housekeeping")
    await rsvc.create_assignment(db, sup.id, rr.id, srv.id, sec.id, "owner")
    await db.flush()

    import freezegun

    with freezegun.freeze_time(now):
        assert clock.now() == now
        rows = await svc.list_staff(db)
        one = await svc.get_staff(db, srv.id)
        unp_one = await svc.get_staff(db, unp.id)
    by_id = {r["account_id"]: r for r in rows}
    assert by_id[srv.id]["on_shift"] is True
    assert by_id[srv.id]["effective_available"] is True
    assert by_id[unp.id]["profile"] is None
    assert by_id[unp.id]["on_shift"] is False
    assert by_id[unp.id]["effective_available"] is False
    assert one["on_shift"] is True and one["effective_available"] is True
    assert unp_one["effective_available"] is False
    assert unp_one["on_shift"] is False

    out_at = now + _dt.timedelta(days=2)
    with freezegun.freeze_time(out_at):
        rows2 = await svc.list_staff(db)
    by_id2 = {r["account_id"]: r for r in rows2}
    assert by_id2[srv.id]["on_shift"] is False
    assert by_id2[srv.id]["effective_available"] is False
