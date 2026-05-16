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
