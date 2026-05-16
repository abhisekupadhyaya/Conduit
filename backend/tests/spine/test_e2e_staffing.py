"""End-to-end staffing journey sentinel (Spec §11).

ONE time-pinned, cross-portal scripted test that *is* the slice: the supervisor
authors the operational staffing structure (roster window + profiled servicer +
skills + a section owner assignment), the servicer's newly-live home renders the
correctly-derived shift, the presence beat flips ``effective_available`` live
(Flow B), the off-shift lock is a real server gate (Flow C: locked + 409 +
yesterday's toggle never bleeds), and disable-not-delete makes a rostered
Working servicer non-routable then re-enable restores (Flow D). Every mutation
along the way leaves exactly one append-only ``Event`` + its typed detail.

It must "break loudly on any pipeline regression" (§11), so the assertions are
specific and ordered, not smoke-level.

Time control (the Task-7 rule, mirrored from ``test_staffing_api.py``)
----------------------------------------------------------------------
Roster windows are created via the supervisor API with EXPLICIT
``shift_start``/``shift_end`` in the request body (NOT ``clock.now()``), so the
supervisor seeding happens UNFROZEN. Business time the servicer derivation reads
flows through ``conduit.core.clock.now()`` — the single call site
``freeze_time`` pins. The JWT ``iat``/``exp`` use the real wall clock, so each
role's ``login`` MUST happen INSIDE the ``freeze_time`` block it is used in: the
cookie is issued and validated at the same frozen instant. When the test shifts
time (in-window → off-shift → back in-window) the servicer re-logs-in under the
new frozen instant.

Exact-count strategy under one savepoint
----------------------------------------
It is ONE test ⇒ ONE shared savepoint ⇒ rows from earlier steps persist within
the test. Every event assertion is therefore SCOPED to a freshly-returned
identifier (the servicer ``account_id``, the roster ``id``, the assignment
``id``) and counts the EXACT cumulative number of detail rows produced so far
for that scope — a delta the script tracks step by step, not an absolute over
the whole DB. Each mutation must add exactly one event + one matching detail.
"""
from __future__ import annotations

import datetime as dt
import uuid

import sqlalchemy as sa
from freezegun import freeze_time

from conduit.shared.models import (
    Event,
    EventAssignmentCreated,
    EventPresenceChanged,
    EventRosterCreated,
    EventStaffProfileCreated,
    EventStaffProfileUpdated,
    EventStaffSkillsSet,
)

_PW = "pw-123456"  # conftest default in make_account / login

# The supervisor-roster bench seeds windows at 2026-05-16 08:00–16:00 UTC.
# These instants sit inside / before that half-open window.
_IN_WINDOW = "2026-05-16T10:00:00+00:00"
_BEFORE_WINDOW = "2026-05-16T06:00:00+00:00"


def _window() -> dict[str, str]:
    start = dt.datetime(2026, 5, 16, 8, 0, tzinfo=dt.UTC)
    end = start + dt.timedelta(hours=8)
    return {"shift_start": start.isoformat(), "shift_end": end.isoformat()}


async def _seed_property_section(db):
    """Inline FK-chain precondition (the migration-test idiom, identical to
    ``test_staffing_api._seed_property_section``): a Property + Section flushed
    (NOT committed) so the single outer savepoint rollback discards it. The
    roster API resolves the single property AD9-style, so a Property must
    physically exist for POST /rosters; a Section must exist to own."""
    from conduit.shared.models import Property, Section

    p = Property(name=f"P-{uuid.uuid4().hex[:8]}")
    db.add(p)
    await db.flush()
    sec = Section(property_id=p.id, label=f"S-{uuid.uuid4().hex[:6]}")
    db.add(sec)
    await db.flush()
    return p, sec


async def _count_detail(db, detail_cls, fk_attr, fk_val) -> int:
    """Cumulative count of one typed detail table scoped to a single fk."""
    rows = (
        await db.execute(
            sa.select(detail_cls).where(getattr(detail_cls, fk_attr) == fk_val)
        )
    ).scalars().all()
    return len(rows)


async def _assert_event_for(db, detail_cls, fk_attr, fk_val, etype, actor_id):
    """Assert exactly ONE detail row for this fk maps to exactly ONE Event of
    ``etype`` authored by ``actor_id``. Scoped, so robust under the shared
    savepoint (each scope sees only its own one mutation of that type)."""
    rows = (
        await db.execute(
            sa.select(detail_cls).where(getattr(detail_cls, fk_attr) == fk_val)
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
    assert str(ev.actor_account_id) == str(actor_id)


async def test_e2e_staffing_sentinel(client, make_account, login, db):
    # ====================================================================
    # Flow 0 / A — supervisor authors the staffing structure (UNFROZEN).
    # Roster window is body-explicit, so no clock dependency on seeding.
    # ====================================================================
    _, sec = await _seed_property_section(db)
    sup = await make_account("supervisor", f"s-{uuid.uuid4().hex[:8]}", _PW)
    srv = await make_account("servicer", f"srv-{uuid.uuid4().hex[:8]}", _PW)
    await login(sup.username, _PW)

    # --- supervisor creates the roster window ---------------------------
    rr = await client.post("/api/supervisor/rosters", json=_window())
    assert rr.status_code == 201, rr.text
    rid = rr.json()["id"]
    assert rr.json()["status"] == "active"
    await db.flush()
    await _assert_event_for(
        db, EventRosterCreated, "roster_id", uuid.UUID(rid),
        "roster_created", sup.id,
    )

    # --- supervisor POSTs a housekeeping profile for the servicer -------
    rp = await client.post(
        f"/api/supervisor/staff/{srv.id}/profile",
        json={"staff_class": "housekeeping"},
    )
    assert rp.status_code == 201, rp.text
    assert rp.json()["profile"]["staff_class"] == "housekeeping"
    assert rp.json()["profile"]["presence"] == "working"
    await db.flush()
    await _assert_event_for(
        db, EventStaffProfileCreated, "account_id", srv.id,
        "staff_profile_created", sup.id,
    )

    # --- supervisor sets skills (the one sanctioned hard-replace) -------
    rs = await client.put(
        f"/api/supervisor/staff/{srv.id}/skills",
        json={"skills": ["linens", "deep_clean"]},
    )
    assert rs.status_code == 200, rs.text
    # The skills replace-set is returned canonicalised (sorted), so compare
    # as sets — the contract guarantees membership, not insertion order.
    assert sorted(rs.json()["skills"]) == ["deep_clean", "linens"]
    await db.flush()
    await _assert_event_for(
        db, EventStaffSkillsSet, "account_id", srv.id,
        "staff_skills_set", sup.id,
    )

    # --- supervisor assigns the servicer owner of the section ----------
    ra = await client.post(
        f"/api/supervisor/rosters/{rid}/assignments",
        json={
            "account_id": str(srv.id),
            "section_id": str(sec.id),
            "assignment": "owner",
        },
    )
    assert ra.status_code == 201, ra.text
    aid = ra.json()["id"]
    assert ra.json()["assignment"] == "owner"
    assert ra.json()["section_id"] == str(sec.id)
    await db.flush()
    await _assert_event_for(
        db, EventAssignmentCreated, "assignment_id", uuid.UUID(aid),
        "assignment_created", sup.id,
    )

    # ====================================================================
    # Flow 0 (cont.) — servicer logs in IN-WINDOW; the live home renders
    # the derived shift and effective_available True (Working default).
    # ====================================================================
    with freeze_time(_IN_WINDOW):
        await login(srv.username, _PW)
        home = await client.get("/api/servicer/home")
    assert home.status_code == 200, home.text
    body = home.json()
    assert body["profile"] is not None
    assert body["profile"]["class"] == "housekeeping"
    assert sorted(body["profile"]["skills"]) == ["deep_clean", "linens"]
    assert sorted(body["skills"]) == ["deep_clean", "linens"]  # top mirror
    assert body["current_shift"] is not None
    assert body["current_shift"]["section_label"] == sec.label
    assert body["current_shift"]["role"] == "owner"
    assert body["presence"] == "working"
    assert body["presence_locked"] is False
    assert body["effective_available"] is True

    # ====================================================================
    # Flow B — the presence beat: working → on_break → working, with
    # effective_available flipping live (derived, never stored).
    # ====================================================================
    with freeze_time(_IN_WINDOW):
        await login(srv.username, _PW)
        rb1 = await client.put(
            "/api/servicer/presence", json={"presence": "on_break"}
        )
    assert rb1.status_code == 200, rb1.text
    assert rb1.json()["presence"] == "on_break"
    assert rb1.json()["effective_available"] is False
    await db.flush()
    assert (
        await _count_detail(db, EventPresenceChanged, "account_id", srv.id)
    ) == 1

    with freeze_time(_IN_WINDOW):
        await login(srv.username, _PW)
        rb2 = await client.put(
            "/api/servicer/presence", json={"presence": "working"}
        )
    assert rb2.status_code == 200, rb2.text
    assert rb2.json()["presence"] == "working"
    assert rb2.json()["effective_available"] is True
    await db.flush()
    assert (
        await _count_detail(db, EventPresenceChanged, "account_id", srv.id)
    ) == 2  # exactly one new presence_changed per PUT

    # ====================================================================
    # Flow C — off-shift proof: time shifted BEFORE the window. Home is
    # locked + effective_available False; PUT /presence → 409 (server
    # gate); the stale in-window Working toggle has NO effect off-shift.
    # ====================================================================
    with freeze_time(_BEFORE_WINDOW):
        await login(srv.username, _PW)
        home_off = await client.get("/api/servicer/home")
        assert home_off.status_code == 200, home_off.text
        off_body = home_off.json()
        assert off_body["current_shift"] is None
        assert off_body["presence_locked"] is True
        # Stale Working set in-window does NOT bleed: derivation reads no
        # window → effective_available False regardless of stored presence.
        assert off_body["effective_available"] is False

        rc = await client.put(
            "/api/servicer/presence", json={"presence": "working"}
        )
    assert rc.status_code == 409, rc.text  # real server lock off-shift
    await db.flush()
    # The 409 mutated nothing: still exactly 2 presence_changed events.
    assert (
        await _count_detail(db, EventPresenceChanged, "account_id", srv.id)
    ) == 2

    # ====================================================================
    # Flow D — disabled staff: supervisor PATCHes status=disabled. Back
    # in-window the rostered + Working servicer is non-routable (status
    # gate); re-enable restores effective_available True. Audit-retained.
    # ====================================================================
    await login(sup.username, _PW)
    rd1 = await client.patch(
        f"/api/supervisor/staff/{srv.id}/profile",
        json={"status": "disabled"},
    )
    assert rd1.status_code == 200, rd1.text
    assert rd1.json()["profile"]["status"] == "disabled"
    await db.flush()
    assert (
        await _count_detail(
            db, EventStaffProfileUpdated, "account_id", srv.id
        )
    ) == 1

    with freeze_time(_IN_WINDOW):
        await login(srv.username, _PW)
        home_dis = await client.get("/api/servicer/home")
    assert home_dis.status_code == 200, home_dis.text
    dis_body = home_dis.json()
    assert dis_body["profile"]["status"] == "disabled"
    # Rostered (current_shift present) + Working, but disabled ⇒ non-routable.
    assert dis_body["current_shift"] is not None
    assert dis_body["presence"] == "working"
    assert dis_body["effective_available"] is False  # disabled gate

    # --- supervisor re-enables → effective_available restored ----------
    await login(sup.username, _PW)
    rd2 = await client.patch(
        f"/api/supervisor/staff/{srv.id}/profile",
        json={"status": "active"},
    )
    assert rd2.status_code == 200, rd2.text
    assert rd2.json()["profile"]["status"] == "active"
    await db.flush()
    # Exactly one MORE staff_profile_updated (disable + re-enable = 2).
    assert (
        await _count_detail(
            db, EventStaffProfileUpdated, "account_id", srv.id
        )
    ) == 2

    with freeze_time(_IN_WINDOW):
        await login(srv.username, _PW)
        home_re = await client.get("/api/servicer/home")
    assert home_re.status_code == 200, home_re.text
    re_body = home_re.json()
    assert re_body["profile"]["status"] == "active"
    assert re_body["current_shift"] is not None
    assert re_body["effective_available"] is True  # re-enable restores

    # ====================================================================
    # Final tally — exactly-one-event-per-mutation across the journey,
    # asserted as scoped cumulative deltas (the §11 append-only invariant).
    # ====================================================================
    assert (
        await _count_detail(db, EventRosterCreated, "roster_id", uuid.UUID(rid))
    ) == 1
    assert (
        await _count_detail(
            db, EventAssignmentCreated, "assignment_id", uuid.UUID(aid)
        )
    ) == 1
    assert (
        await _count_detail(
            db, EventStaffProfileCreated, "account_id", srv.id
        )
    ) == 1
    assert (
        await _count_detail(db, EventStaffSkillsSet, "account_id", srv.id)
    ) == 1
    assert (
        await _count_detail(
            db, EventStaffProfileUpdated, "account_id", srv.id
        )
    ) == 2  # disable + re-enable
    assert (
        await _count_detail(db, EventPresenceChanged, "account_id", srv.id)
    ) == 2  # on_break + working (the 409 wrote nothing)
