# tests/binding/test_api.py
import uuid
import pytest


@pytest.fixture()
async def sup(make_account, login, seeded_property):
    await make_account("supervisor", "sup-api", "pw-123456")
    await login("sup-api", "pw-123456")


async def test_sections_rooms_flow(client, sup):
    r = await client.post("/api/supervisor/sections", json={"label": "North"})
    assert r.status_code == 201, r.text
    sid = r.json()["id"]
    assert (await client.get("/api/supervisor/sections")).status_code == 200
    assert (await client.post("/api/supervisor/sections",
                              json={"label": "north"})).status_code == 409
    rn = await client.patch(f"/api/supervisor/sections/{sid}",
                            json={"label": "N"})
    assert rn.status_code == 200 and rn.json()["label"] == "N"
    rm = await client.post("/api/supervisor/rooms",
                           json={"label": "304", "section_id": sid})
    assert rm.status_code == 201
    assert (await client.get(
        f"/api/supervisor/rooms?section_id={sid}")).status_code == 200
    assert (await client.delete(
        f"/api/supervisor/sections/{sid}")).status_code == 405


async def test_stays_flow(client, sup):
    sid = (await client.post("/api/supervisor/sections",
                             json={"label": "N"})).json()["id"]
    rid = (await client.post("/api/supervisor/rooms",
                             json={"label": "304", "section_id": sid}
                             )).json()["id"]
    rid2 = (await client.post("/api/supervisor/rooms",
                              json={"label": "511", "section_id": sid}
                              )).json()["id"]
    g = (await client.post("/api/supervisor/accounts", json={
        "role": "guest", "username": f"g{uuid.uuid4().hex[:8]}",
        "display_name": "G", "password": "pw-123456"})).json()["id"]
    st = (await client.post("/api/supervisor/stays", json={
        "guest_account_id": g, "room_id": rid,
        "check_in": "2026-05-16T14:00:00Z",
        "check_out": "2026-05-19T11:00:00Z"})).json()["id"]
    assert (await client.post("/api/supervisor/stays", json={
        "guest_account_id": g, "room_id": rid,
        "check_in": "2026-05-16T14:00:00Z",
        "check_out": "2026-05-19T11:00:00Z"})).status_code == 409
    mv = await client.post(f"/api/supervisor/stays/{st}/relocate",
                           json={"new_room_id": rid2})
    assert mv.status_code == 200 and mv.json()["room_id"] == rid2
    assert (await client.post(f"/api/supervisor/stays/{st}/relocate",
                              json={"new_room_id": rid2})).status_code == 409
    co = await client.post(f"/api/supervisor/stays/{st}/checkout")
    assert co.status_code == 200 and co.json()["status"] == "ended"
    assert (await client.post(
        f"/api/supervisor/stays/{uuid.uuid4()}/checkout")).status_code == 404


async def test_unauth_and_forbidden(client, make_account, login):
    assert (await client.get("/api/supervisor/sections")).status_code == 401
    await make_account("guest", "g-forbid", "pw-123456")
    await login("g-forbid", "pw-123456")
    assert (await client.get("/api/supervisor/sections")).status_code == 403
