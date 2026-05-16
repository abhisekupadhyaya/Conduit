# tests/binding/test_invariants.py
import uuid
import pytest
from sqlalchemy import text
from conduit.supervisor.dal import sections as sdal, rooms as rdal


async def test_partial_unique_index_blocks_second_active(
    db, seeded_property, make_account,
):
    g = await make_account("guest", "g-inv-1")
    s = await sdal.insert_section(db, seeded_property.id, "N")
    await db.flush()
    r = await rdal.insert_room(db, s.id, "304")
    await db.flush()
    _ins = text(
        "insert into stay (guest_account_id,room_id,check_in,check_out,"
        "status) values (:g,:r,now(),now(),'active')")
    await db.execute(_ins, {"g": str(g.id), "r": str(r.id)})
    with pytest.raises(Exception):
        await db.execute(_ins, {"g": str(g.id), "r": str(r.id)})
    await db.rollback()


async def test_event_dal_has_no_mutation_path():
    from conduit.supervisor.dal import events as edal
    assert not any(n.startswith(("update_", "delete_")) for n in dir(edal))


async def test_section_is_derived_no_stay_write(
    client, make_account, login,
):
    await make_account("supervisor", "sup-inv", "pw-123456")
    await login("sup-inv", "pw-123456")
    sid = (await client.post("/api/supervisor/sections",
                             json={"label": "N"})).json()["id"]
    rid = (await client.post("/api/supervisor/rooms",
                             json={"label": "304", "section_id": sid}
                             )).json()["id"]
    sid2 = (await client.post("/api/supervisor/sections",
                              json={"label": "S"})).json()["id"]
    uname = f"g{uuid.uuid4().hex[:8]}"
    g = (await client.post("/api/supervisor/accounts", json={
        "role": "guest", "username": uname, "display_name": "G",
        "password": "pw-123456"})).json()["id"]
    await client.post("/api/supervisor/stays", json={
        "guest_account_id": g, "room_id": rid,
        "check_in": "2026-05-16T14:00:00Z",
        "check_out": "2026-05-19T11:00:00Z"})
    await login(uname, "pw-123456")
    assert (await client.get("/api/auth/me")).json()["section_label"] == "N"
    await login("sup-inv", "pw-123456")
    await client.patch(f"/api/supervisor/rooms/{rid}",
                       json={"section_id": sid2})
    await login(uname, "pw-123456")
    assert (await client.get("/api/auth/me")).json()["section_label"] == "S"
