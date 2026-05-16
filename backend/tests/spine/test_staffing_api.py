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
