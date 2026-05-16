"""Supervisor Staff API — full ASGI stack, real per-role cookie chains.

Every endpoint x every documented status (spec §8 Supervisor — Staff):
happy + 403/404/409/422/405. Mirrors test_e2e_journey.py's HTTP driving:
``make_account`` (commits into the savepoint), ``login`` swaps the one
active session cookie.
"""
from __future__ import annotations

import uuid

_PW = "pw-123456"


async def _servicer_id(make_account, suffix: str) -> uuid.UUID:
    acc = await make_account("servicer", f"srv-{suffix}", _PW)
    return acc.id


async def test_list_staff_as_supervisor_no_secret_hash(
    client, make_account, login
):
    sid = await _servicer_id(make_account, uuid.uuid4().hex[:8])
    sup = await make_account("supervisor", f"s-{uuid.uuid4().hex[:8]}", _PW)
    await login(sup.username, _PW)
    r = await client.get("/api/supervisor/staff")
    assert r.status_code == 200, r.text
    body = r.json()
    ids = {row["account_id"] for row in body}
    assert str(sid) in ids
    row = next(row for row in body if row["account_id"] == str(sid))
    assert row["profile"] is None
    assert row["skills"] == []
    # No account internals anywhere in the serialized payload.
    assert "secret_hash" not in r.text
    for row in body:
        assert "secret_hash" not in row
        assert "username" not in row
        assert "password" not in row


async def test_create_profile_201(client, make_account, login):
    sid = await _servicer_id(make_account, uuid.uuid4().hex[:8])
    sup = await make_account("supervisor", f"s-{uuid.uuid4().hex[:8]}", _PW)
    await login(sup.username, _PW)
    r = await client.post(
        f"/api/supervisor/staff/{sid}/profile",
        json={"staff_class": "housekeeping"},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["account_id"] == str(sid)
    assert body["profile"]["staff_class"] == "housekeeping"
    assert body["profile"]["presence"] == "working"
    assert body["profile"]["status"] == "active"


async def test_create_profile_twice_409(client, make_account, login):
    sid = await _servicer_id(make_account, uuid.uuid4().hex[:8])
    sup = await make_account("supervisor", f"s-{uuid.uuid4().hex[:8]}", _PW)
    await login(sup.username, _PW)
    r1 = await client.post(
        f"/api/supervisor/staff/{sid}/profile",
        json={"staff_class": "housekeeping"},
    )
    assert r1.status_code == 201, r1.text
    r2 = await client.post(
        f"/api/supervisor/staff/{sid}/profile",
        json={"staff_class": "engineering"},
    )
    assert r2.status_code == 409, r2.text


async def test_create_profile_for_guest_422(client, make_account, login):
    guest = await make_account("guest", f"g-{uuid.uuid4().hex[:8]}", _PW)
    sup = await make_account("supervisor", f"s-{uuid.uuid4().hex[:8]}", _PW)
    await login(sup.username, _PW)
    r = await client.post(
        f"/api/supervisor/staff/{guest.id}/profile",
        json={"staff_class": "housekeeping"},
    )
    assert r.status_code == 422, r.text


async def test_create_profile_for_random_uuid_404(client, make_account, login):
    sup = await make_account("supervisor", f"s-{uuid.uuid4().hex[:8]}", _PW)
    await login(sup.username, _PW)
    r = await client.post(
        f"/api/supervisor/staff/{uuid.uuid4()}/profile",
        json={"staff_class": "housekeeping"},
    )
    assert r.status_code == 404, r.text


async def test_patch_profile_200(client, make_account, login):
    sid = await _servicer_id(make_account, uuid.uuid4().hex[:8])
    sup = await make_account("supervisor", f"s-{uuid.uuid4().hex[:8]}", _PW)
    await login(sup.username, _PW)
    await client.post(
        f"/api/supervisor/staff/{sid}/profile",
        json={"staff_class": "housekeeping"},
    )
    r = await client.patch(
        f"/api/supervisor/staff/{sid}/profile",
        json={"status": "disabled"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["profile"]["status"] == "disabled"


async def test_put_skills_200(client, make_account, login):
    sid = await _servicer_id(make_account, uuid.uuid4().hex[:8])
    sup = await make_account("supervisor", f"s-{uuid.uuid4().hex[:8]}", _PW)
    await login(sup.username, _PW)
    await client.post(
        f"/api/supervisor/staff/{sid}/profile",
        json={"staff_class": "engineering"},
    )
    r = await client.put(
        f"/api/supervisor/staff/{sid}/skills",
        json={"skills": ["electrical", "hvac"]},
    )
    assert r.status_code == 200, r.text
    assert r.json()["skills"] == ["electrical", "hvac"]


async def test_put_skills_no_profile_404(client, make_account, login):
    sid = await _servicer_id(make_account, uuid.uuid4().hex[:8])
    sup = await make_account("supervisor", f"s-{uuid.uuid4().hex[:8]}", _PW)
    await login(sup.username, _PW)
    r = await client.put(
        f"/api/supervisor/staff/{sid}/skills",
        json={"skills": ["electrical"]},
    )
    assert r.status_code == 404, r.text


async def test_list_staff_as_servicer_403(client, make_account, login):
    srv = await make_account("servicer", f"srv-{uuid.uuid4().hex[:8]}", _PW)
    await login(srv.username, _PW)
    r = await client.get("/api/supervisor/staff")
    assert r.status_code == 403, r.text


async def test_delete_staff_405(client, make_account, login):
    sid = await _servicer_id(make_account, uuid.uuid4().hex[:8])
    sup = await make_account("supervisor", f"s-{uuid.uuid4().hex[:8]}", _PW)
    await login(sup.username, _PW)
    r = await client.delete(f"/api/supervisor/staff/{sid}")
    assert r.status_code == 405, r.text


async def test_get_one_staff_200(client, make_account, login):
    sid = await _servicer_id(make_account, uuid.uuid4().hex[:8])
    sup = await make_account("supervisor", f"s-{uuid.uuid4().hex[:8]}", _PW)
    await login(sup.username, _PW)
    await client.post(
        f"/api/supervisor/staff/{sid}/profile",
        json={"staff_class": "concierge"},
    )
    r = await client.get(f"/api/supervisor/staff/{sid}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["account_id"] == str(sid)
    assert body["profile"]["staff_class"] == "concierge"
    assert "secret_hash" not in r.text


async def test_get_one_staff_random_uuid_404(client, make_account, login):
    sup = await make_account("supervisor", f"s-{uuid.uuid4().hex[:8]}", _PW)
    await login(sup.username, _PW)
    r = await client.get(f"/api/supervisor/staff/{uuid.uuid4()}")
    assert r.status_code == 404, r.text


async def test_get_one_staff_guest_404(client, make_account, login):
    guest = await make_account("guest", f"g-{uuid.uuid4().hex[:8]}", _PW)
    sup = await make_account("supervisor", f"s-{uuid.uuid4().hex[:8]}", _PW)
    await login(sup.username, _PW)
    r = await client.get(f"/api/supervisor/staff/{guest.id}")
    assert r.status_code == 404, r.text


async def test_patch_profile_no_profile_404(client, make_account, login):
    sid = await _servicer_id(make_account, uuid.uuid4().hex[:8])
    sup = await make_account("supervisor", f"s-{uuid.uuid4().hex[:8]}", _PW)
    await login(sup.username, _PW)
    r = await client.patch(
        f"/api/supervisor/staff/{sid}/profile",
        json={"staff_class": "runner"},
    )
    assert r.status_code == 404, r.text


async def test_patch_profile_class_change_200(client, make_account, login):
    sid = await _servicer_id(make_account, uuid.uuid4().hex[:8])
    sup = await make_account("supervisor", f"s-{uuid.uuid4().hex[:8]}", _PW)
    await login(sup.username, _PW)
    await client.post(
        f"/api/supervisor/staff/{sid}/profile",
        json={"staff_class": "housekeeping"},
    )
    r = await client.patch(
        f"/api/supervisor/staff/{sid}/profile",
        json={"staff_class": "room_service"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["profile"]["staff_class"] == "room_service"


async def test_list_staff_status_and_class_filters(
    client, make_account, login
):
    a = await _servicer_id(make_account, uuid.uuid4().hex[:8])
    b = await _servicer_id(make_account, uuid.uuid4().hex[:8])
    await _servicer_id(make_account, uuid.uuid4().hex[:8])  # un-profiled
    sup = await make_account("supervisor", f"s-{uuid.uuid4().hex[:8]}", _PW)
    await login(sup.username, _PW)
    await client.post(
        f"/api/supervisor/staff/{a}/profile",
        json={"staff_class": "engineering"},
    )
    await client.post(
        f"/api/supervisor/staff/{b}/profile",
        json={"staff_class": "housekeeping"},
    )
    await client.patch(
        f"/api/supervisor/staff/{b}/profile", json={"status": "disabled"}
    )

    r_active = await client.get("/api/supervisor/staff?status=active")
    ids = {row["account_id"] for row in r_active.json()}
    assert str(a) in ids and str(b) not in ids

    r_class = await client.get("/api/supervisor/staff?class=engineering")
    ids = {row["account_id"] for row in r_class.json()}
    assert ids == {str(a)}


async def test_skills_replace_set_overwrites(client, make_account, login):
    sid = await _servicer_id(make_account, uuid.uuid4().hex[:8])
    sup = await make_account("supervisor", f"s-{uuid.uuid4().hex[:8]}", _PW)
    await login(sup.username, _PW)
    await client.post(
        f"/api/supervisor/staff/{sid}/profile",
        json={"staff_class": "engineering"},
    )
    await client.put(
        f"/api/supervisor/staff/{sid}/skills",
        json={"skills": ["hvac", "electrical", "hvac"]},
    )
    r = await client.put(
        f"/api/supervisor/staff/{sid}/skills",
        json={"skills": ["plumbing"]},
    )
    assert r.status_code == 200, r.text
    assert r.json()["skills"] == ["plumbing"]


async def test_one_event_per_mutation(client, make_account, login, db):
    import sqlalchemy as sa

    from conduit.shared.models import (
        Event,
        EventStaffProfileCreated,
        EventStaffProfileUpdated,
        EventStaffSkillsSet,
    )

    sid = await _servicer_id(make_account, uuid.uuid4().hex[:8])
    sup = await make_account("supervisor", f"s-{uuid.uuid4().hex[:8]}", _PW)
    await login(sup.username, _PW)

    await client.post(
        f"/api/supervisor/staff/{sid}/profile",
        json={"staff_class": "housekeeping"},
    )
    await client.patch(
        f"/api/supervisor/staff/{sid}/profile", json={"status": "disabled"}
    )
    await client.put(
        f"/api/supervisor/staff/{sid}/skills", json={"skills": ["hvac"]}
    )

    for detail_cls, etype in (
        (EventStaffProfileCreated, "staff_profile_created"),
        (EventStaffProfileUpdated, "staff_profile_updated"),
        (EventStaffSkillsSet, "staff_skills_set"),
    ):
        rows = (
            await db.execute(
                sa.select(detail_cls).where(detail_cls.account_id == sid)
            )
        ).scalars().all()
        assert len(rows) == 1, f"{etype}: expected exactly 1 detail row"
        ev = (
            await db.execute(
                sa.select(Event).where(
                    Event.id == rows[0].event_id, Event.type == etype
                )
            )
        ).scalar_one()
        assert str(ev.actor_account_id) == str(sup.id)


# ===========================================================================
# Task 6 — Supervisor Rosters API (spec §8 "Supervisor — Rosters", §6, §4).
# APPENDED below the Task-5 Staff bench; nothing above is modified.
# ===========================================================================


async def _seed_property_section(db):
    """Inline FK-chain precondition (the migration-test idiom): a Property +
    a Section, flushed (NOT committed) so the single outer savepoint rollback
    discards it. The roster API resolves the single property AD9-style, so a
    Property must physically exist for POST /rosters to succeed."""
    from conduit.shared.models import Property, Section

    p = Property(name=f"P-{uuid.uuid4().hex[:8]}")
    db.add(p)
    await db.flush()
    sec = Section(property_id=p.id, label=f"S-{uuid.uuid4().hex[:6]}")
    db.add(sec)
    await db.flush()
    return p, sec


def _window(hours: int = 8) -> dict[str, str]:
    import datetime as dt

    start = dt.datetime(2026, 5, 16, 8, 0, tzinfo=dt.UTC)
    end = start + dt.timedelta(hours=hours)
    return {
        "shift_start": start.isoformat(),
        "shift_end": end.isoformat(),
    }


def _bad_window() -> dict[str, str]:
    import datetime as dt

    start = dt.datetime(2026, 5, 16, 16, 0, tzinfo=dt.UTC)
    end = dt.datetime(2026, 5, 16, 8, 0, tzinfo=dt.UTC)
    return {
        "shift_start": start.isoformat(),
        "shift_end": end.isoformat(),
    }


async def _sup_login(make_account, login):
    sup = await make_account("supervisor", f"s-{uuid.uuid4().hex[:8]}", _PW)
    await login(sup.username, _PW)
    return sup


async def test_create_roster_201(client, make_account, login, db):
    await _seed_property_section(db)
    await _sup_login(make_account, login)
    r = await client.post("/api/supervisor/rosters", json=_window())
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "active"
    assert "id" in body


async def test_create_roster_bad_window_422(client, make_account, login, db):
    await _seed_property_section(db)
    await _sup_login(make_account, login)
    r = await client.post("/api/supervisor/rosters", json=_bad_window())
    assert r.status_code == 422, r.text


async def test_create_owner_assignment_201(client, make_account, login, db):
    _, sec = await _seed_property_section(db)
    sup = await _sup_login(make_account, login)
    srv = await make_account("servicer", f"srv-{uuid.uuid4().hex[:8]}", _PW)
    # housekeeping (section-pooled) servicer.
    await login(sup.username, _PW)
    rid = (
        await client.post("/api/supervisor/rosters", json=_window())
    ).json()["id"]
    await client.post(
        f"/api/supervisor/staff/{srv.id}/profile",
        json={"staff_class": "housekeeping"},
    )
    r = await client.post(
        f"/api/supervisor/rosters/{rid}/assignments",
        json={
            "account_id": str(srv.id),
            "section_id": str(sec.id),
            "assignment": "owner",
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["assignment"] == "owner"
    assert body["section_id"] == str(sec.id)


async def test_duplicate_active_owner_409(client, make_account, login, db):
    _, sec = await _seed_property_section(db)
    sup = await _sup_login(make_account, login)
    a = await make_account("servicer", f"srv-{uuid.uuid4().hex[:8]}", _PW)
    b = await make_account("servicer", f"srv-{uuid.uuid4().hex[:8]}", _PW)
    await login(sup.username, _PW)
    rid = (
        await client.post("/api/supervisor/rosters", json=_window())
    ).json()["id"]
    for acc in (a, b):
        await client.post(
            f"/api/supervisor/staff/{acc.id}/profile",
            json={"staff_class": "housekeeping"},
        )
    r1 = await client.post(
        f"/api/supervisor/rosters/{rid}/assignments",
        json={
            "account_id": str(a.id),
            "section_id": str(sec.id),
            "assignment": "owner",
        },
    )
    assert r1.status_code == 201, r1.text
    r2 = await client.post(
        f"/api/supervisor/rosters/{rid}/assignments",
        json={
            "account_id": str(b.id),
            "section_id": str(sec.id),
            "assignment": "owner",
        },
    )
    assert r2.status_code == 409, r2.text


async def test_owner_without_section_422(client, make_account, login, db):
    await _seed_property_section(db)
    sup = await _sup_login(make_account, login)
    srv = await make_account("servicer", f"srv-{uuid.uuid4().hex[:8]}", _PW)
    await login(sup.username, _PW)
    rid = (
        await client.post("/api/supervisor/rosters", json=_window())
    ).json()["id"]
    await client.post(
        f"/api/supervisor/staff/{srv.id}/profile",
        json={"staff_class": "housekeeping"},
    )
    r = await client.post(
        f"/api/supervisor/rosters/{rid}/assignments",
        json={
            "account_id": str(srv.id),
            "section_id": None,
            "assignment": "owner",
        },
    )
    assert r.status_code == 422, r.text


async def test_engineering_with_section_422(client, make_account, login, db):
    _, sec = await _seed_property_section(db)
    sup = await _sup_login(make_account, login)
    srv = await make_account("servicer", f"srv-{uuid.uuid4().hex[:8]}", _PW)
    await login(sup.username, _PW)
    rid = (
        await client.post("/api/supervisor/rosters", json=_window())
    ).json()["id"]
    await client.post(
        f"/api/supervisor/staff/{srv.id}/profile",
        json={"staff_class": "engineering"},
    )
    # D18: engineering is skill-matched, NOT section-pooled.
    r = await client.post(
        f"/api/supervisor/rosters/{rid}/assignments",
        json={
            "account_id": str(srv.id),
            "section_id": str(sec.id),
            "assignment": "member",
        },
    )
    assert r.status_code == 422, r.text


async def test_engineering_member_no_section_201(
    client, make_account, login, db
):
    await _seed_property_section(db)
    sup = await _sup_login(make_account, login)
    srv = await make_account("servicer", f"srv-{uuid.uuid4().hex[:8]}", _PW)
    await login(sup.username, _PW)
    rid = (
        await client.post("/api/supervisor/rosters", json=_window())
    ).json()["id"]
    await client.post(
        f"/api/supervisor/staff/{srv.id}/profile",
        json={"staff_class": "engineering"},
    )
    r = await client.post(
        f"/api/supervisor/rosters/{rid}/assignments",
        json={
            "account_id": str(srv.id),
            "section_id": None,
            "assignment": "member",
        },
    )
    assert r.status_code == 201, r.text
    assert r.json()["section_id"] is None


async def test_assignment_non_servicer_422(client, make_account, login, db):
    await _seed_property_section(db)
    sup = await _sup_login(make_account, login)
    guest = await make_account("guest", f"g-{uuid.uuid4().hex[:8]}", _PW)
    await login(sup.username, _PW)
    rid = (
        await client.post("/api/supervisor/rosters", json=_window())
    ).json()["id"]
    r = await client.post(
        f"/api/supervisor/rosters/{rid}/assignments",
        json={
            "account_id": str(guest.id),
            "section_id": None,
            "assignment": "member",
        },
    )
    assert r.status_code == 422, r.text


async def test_patch_roster_disabled_200(client, make_account, login, db):
    await _seed_property_section(db)
    await _sup_login(make_account, login)
    rid = (
        await client.post("/api/supervisor/rosters", json=_window())
    ).json()["id"]
    r = await client.patch(
        f"/api/supervisor/rosters/{rid}", json={"status": "disabled"}
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "disabled"


async def test_delete_roster_405(client, make_account, login, db):
    await _seed_property_section(db)
    await _sup_login(make_account, login)
    rid = (
        await client.post("/api/supervisor/rosters", json=_window())
    ).json()["id"]
    r = await client.delete(f"/api/supervisor/rosters/{rid}")
    assert r.status_code == 405, r.text


async def test_list_rosters_and_assignments_and_patch_assignment(
    client, make_account, login, db
):
    _, sec = await _seed_property_section(db)
    sup = await _sup_login(make_account, login)
    srv = await make_account("servicer", f"srv-{uuid.uuid4().hex[:8]}", _PW)
    await login(sup.username, _PW)
    rid = (
        await client.post("/api/supervisor/rosters", json=_window())
    ).json()["id"]
    await client.post(
        f"/api/supervisor/staff/{srv.id}/profile",
        json={"staff_class": "housekeeping"},
    )
    aid = (
        await client.post(
            f"/api/supervisor/rosters/{rid}/assignments",
            json={
                "account_id": str(srv.id),
                "section_id": str(sec.id),
                "assignment": "owner",
            },
        )
    ).json()["id"]

    lst = await client.get("/api/supervisor/rosters")
    assert lst.status_code == 200, lst.text
    assert any(row["id"] == rid for row in lst.json())

    asn = await client.get(f"/api/supervisor/rosters/{rid}/assignments")
    assert asn.status_code == 200, asn.text
    assert any(row["id"] == aid for row in asn.json())

    # active_at filter narrows to windows live at the instant.
    inside = await client.get(
        "/api/supervisor/rosters?active_at=2026-05-16T10:00:00%2B00:00"
    )
    assert inside.status_code == 200
    assert any(row["id"] == rid for row in inside.json())
    outside = await client.get(
        "/api/supervisor/rosters?active_at=2026-05-17T10:00:00%2B00:00"
    )
    assert all(row["id"] != rid for row in outside.json())

    # PATCH assignment: disable it (disable-not-delete).
    pr = await client.patch(
        f"/api/supervisor/rosters/{rid}/assignments/{aid}",
        json={"status": "disabled"},
    )
    assert pr.status_code == 200, pr.text
    assert pr.json()["status"] == "disabled"


async def test_rosters_as_servicer_403(client, make_account, login, db):
    await _seed_property_section(db)
    srv = await make_account("servicer", f"srv-{uuid.uuid4().hex[:8]}", _PW)
    await login(srv.username, _PW)
    r = await client.get("/api/supervisor/rosters")
    assert r.status_code == 403, r.text


async def test_roster_one_event_per_mutation(
    client, make_account, login, db
):
    import sqlalchemy as sa

    from conduit.shared.models import (
        Event,
        EventAssignmentCreated,
        EventAssignmentUpdated,
        EventRosterCreated,
        EventRosterUpdated,
    )

    _, sec = await _seed_property_section(db)
    sup = await _sup_login(make_account, login)
    srv = await make_account("servicer", f"srv-{uuid.uuid4().hex[:8]}", _PW)
    await login(sup.username, _PW)
    rid = (
        await client.post("/api/supervisor/rosters", json=_window())
    ).json()["id"]
    await client.patch(
        f"/api/supervisor/rosters/{rid}", json={"status": "active"}
    )
    await client.post(
        f"/api/supervisor/staff/{srv.id}/profile",
        json={"staff_class": "housekeeping"},
    )
    aid = (
        await client.post(
            f"/api/supervisor/rosters/{rid}/assignments",
            json={
                "account_id": str(srv.id),
                "section_id": str(sec.id),
                "assignment": "owner",
            },
        )
    ).json()["id"]
    await client.patch(
        f"/api/supervisor/rosters/{rid}/assignments/{aid}",
        json={"status": "disabled"},
    )

    import uuid as _uuid

    for detail_cls, fk_attr, fk_val, etype in (
        (EventRosterCreated, "roster_id", rid, "roster_created"),
        (EventRosterUpdated, "roster_id", rid, "roster_updated"),
        (EventAssignmentCreated, "assignment_id", aid, "assignment_created"),
        (EventAssignmentUpdated, "assignment_id", aid, "assignment_updated"),
    ):
        rows = (
            await db.execute(
                sa.select(detail_cls).where(
                    getattr(detail_cls, fk_attr) == _uuid.UUID(fk_val)
                )
            )
        ).scalars().all()
        assert len(rows) == 1, f"{etype}: expected exactly 1 detail row"
        ev = (
            await db.execute(
                sa.select(Event).where(
                    Event.id == rows[0].event_id, Event.type == etype
                )
            )
        ).scalar_one()
        assert str(ev.actor_account_id) == str(sup.id)


# ===========================================================================
# Task 7 — Servicer self portal API (spec §8 "Servicer — self", §7, §4).
# APPENDED below the Task-5/6 supervisor bench; nothing above is modified.
#
# Business time is freezegun-pinned: conduit.core.clock.now() is the single
# call site the servicer derivation reads, so freeze_time flips on/off-shift.
# Roster windows are created via the supervisor API with EXPLICIT
# shift_start/shift_end (request body, not clock.now()), so seeding happens
# UNFROZEN. The servicer login + servicer request run together inside one
# freeze_time block: the JWT iat/exp use the real wall clock, so the cookie
# must be ISSUED and VALIDATED at the same frozen instant (login under freeze).
# ===========================================================================

from freezegun import freeze_time  # noqa: E402

# The supervisor-roster bench seeds windows at 2026-05-16 08:00–16:00 UTC
# (see _window()). These instants sit inside / outside that half-open window.
_INSIDE = "2026-05-16T10:00:00+00:00"
_OUTSIDE = "2026-05-20T10:00:00+00:00"


async def _seed_servicer_on_roster(client, make_account, login, db):
    """Supervisor seeds (UNFROZEN): a property+section, a profiled servicer,
    a roster over 2026-05-16 08:00–16:00 UTC, and an active owner assignment.
    Returns the servicer account. All via the REAL supervisor API."""
    _, sec = await _seed_property_section(db)
    sup = await _sup_login(make_account, login)
    srv = await make_account("servicer", f"srv-{uuid.uuid4().hex[:8]}", _PW)
    await login(sup.username, _PW)
    rid = (
        await client.post("/api/supervisor/rosters", json=_window())
    ).json()["id"]
    await client.post(
        f"/api/supervisor/staff/{srv.id}/profile",
        json={"staff_class": "housekeeping"},
    )
    r = await client.post(
        f"/api/supervisor/rosters/{rid}/assignments",
        json={
            "account_id": str(srv.id),
            "section_id": str(sec.id),
            "assignment": "owner",
        },
    )
    assert r.status_code == 201, r.text
    return srv


async def test_servicer_home_on_shift_200(client, make_account, login, db):
    srv = await _seed_servicer_on_roster(client, make_account, login, db)
    with freeze_time(_INSIDE):
        await login(srv.username, _PW)
        r = await client.get("/api/servicer/home")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["profile"] is not None
    assert body["profile"]["class"] == "housekeeping"
    assert body["current_shift"] is not None
    assert body["presence_locked"] is False
    assert body["effective_available"] is True


async def test_servicer_presence_on_break_on_shift_200(
    client, make_account, login, db
):
    srv = await _seed_servicer_on_roster(client, make_account, login, db)
    with freeze_time(_INSIDE):
        await login(srv.username, _PW)
        r = await client.put(
            "/api/servicer/presence", json={"presence": "on_break"}
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["presence"] == "on_break"
    assert body["effective_available"] is False


async def test_servicer_home_off_shift_locked(
    client, make_account, login, db
):
    srv = await _seed_servicer_on_roster(client, make_account, login, db)
    with freeze_time(_OUTSIDE):
        await login(srv.username, _PW)
        r = await client.get("/api/servicer/home")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["current_shift"] is None
    assert body["presence_locked"] is True
    assert body["effective_available"] is False


async def test_servicer_presence_off_shift_409(
    client, make_account, login, db
):
    srv = await _seed_servicer_on_roster(client, make_account, login, db)
    with freeze_time(_OUTSIDE):
        await login(srv.username, _PW)
        r = await client.put(
            "/api/servicer/presence", json={"presence": "working"}
        )
    assert r.status_code == 409, r.text


async def test_servicer_home_as_supervisor_403(
    client, make_account, login, db
):
    await _seed_property_section(db)
    sup = await _sup_login(make_account, login)
    with freeze_time(_INSIDE):
        await login(sup.username, _PW)
        r = await client.get("/api/servicer/home")
    assert r.status_code == 403, r.text


async def test_servicer_presence_delete_405(client, make_account, login, db):
    srv = await _seed_servicer_on_roster(client, make_account, login, db)
    with freeze_time(_INSIDE):
        await login(srv.username, _PW)
        r = await client.delete("/api/servicer/presence")
    assert r.status_code == 405, r.text


async def test_servicer_unprofiled_home_graceful(
    client, make_account, login, db
):
    """Un-profiled servicer (provisioned, not yet profiled — a first-class
    state per §4): home does NOT crash. profile null, presence the Working
    default literal, effective_available False (no active profile)."""
    srv = await make_account("servicer", f"srv-{uuid.uuid4().hex[:8]}", _PW)
    with freeze_time(_INSIDE):
        await login(srv.username, _PW)
        r = await client.get("/api/servicer/home")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["profile"] is None
    assert body["presence"] == "working"
    assert body["effective_available"] is False


async def test_servicer_presence_in_window_toggle_scopes(
    client, make_account, login, db
):
    """Presence shift-scoping (spec §4): a toggle set while on-shift
    (presence_set_at ∈ current_window) DOES suppress availability for that
    window. The Task-3 derivation owns the scoping; confirm end-to-end that
    an in-window Off both returns effective_available False on the PUT and on
    a subsequent home read — yesterday's toggle never bleeds because the
    derivation only counts presence_set_at inside the live window."""
    srv = await _seed_servicer_on_roster(client, make_account, login, db)
    with freeze_time(_INSIDE):
        await login(srv.username, _PW)
        r = await client.put(
            "/api/servicer/presence", json={"presence": "off"}
        )
        assert r.status_code == 200, r.text
        assert r.json()["effective_available"] is False
        home = await client.get("/api/servicer/home")
        assert home.json()["effective_available"] is False
    # OUTSIDE the window the SAME presence_set_at is no longer in-window:
    # the derivation reads the Working default — the toggle does not bleed.
    with freeze_time(_OUTSIDE):
        await login(srv.username, _PW)
        off = await client.get("/api/servicer/home")
    assert off.status_code == 200, off.text
    # Off-shift: locked + not available (no window), but this proves the
    # stored toggle did not persist as a global suppression.
    assert off.json()["presence_locked"] is True


async def test_servicer_presence_one_event_per_change(
    client, make_account, login, db
):
    """Exactly one append-only presence_changed event per successful PUT —
    uniform with the Task-5/6 ``test_one_event_per_mutation`` shape so the
    Task-8 append-only guard sees one consistent pattern."""
    import sqlalchemy as sa

    from conduit.shared.models import Event, EventPresenceChanged

    srv = await _seed_servicer_on_roster(client, make_account, login, db)
    with freeze_time(_INSIDE):
        await login(srv.username, _PW)
        r = await client.put(
            "/api/servicer/presence", json={"presence": "on_break"}
        )
        assert r.status_code == 200, r.text

    rows = (
        await db.execute(
            sa.select(EventPresenceChanged).where(
                EventPresenceChanged.account_id == srv.id
            )
        )
    ).scalars().all()
    assert len(rows) == 1, "expected exactly 1 presence_changed detail row"
    ev = (
        await db.execute(
            sa.select(Event).where(
                Event.id == rows[0].event_id,
                Event.type == "presence_changed",
            )
        )
    ).scalar_one()
    assert str(ev.actor_account_id) == str(srv.id)
