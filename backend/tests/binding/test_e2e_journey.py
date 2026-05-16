# tests/binding/test_e2e_journey.py
import uuid


async def test_full_journey(client, make_account, login):
    await make_account("supervisor", "sup-e2e", "pw-123456")
    await login("sup-e2e", "pw-123456")
    s1 = (await client.post("/api/supervisor/sections",
                            json={"label": "North"})).json()["id"]
    r1 = (await client.post("/api/supervisor/rooms",
                            json={"label": "304", "section_id": s1}
                            )).json()["id"]
    s2 = (await client.post("/api/supervisor/sections",
                            json={"label": "South"})).json()["id"]
    r2 = (await client.post("/api/supervisor/rooms",
                            json={"label": "511", "section_id": s2}
                            )).json()["id"]
    uname = f"g{uuid.uuid4().hex[:8]}"
    g = (await client.post("/api/supervisor/accounts", json={
        "role": "guest", "username": uname, "display_name": "Guest",
        "password": "pw-123456"})).json()["id"]
    st = (await client.post("/api/supervisor/stays", json={
        "guest_account_id": g, "room_id": r1,
        "check_in": "2026-05-16T14:00:00Z",
        "check_out": "2026-05-19T11:00:00Z"})).json()["id"]

    await login(uname, "pw-123456")
    me = (await client.get("/api/auth/me")).json()
    assert me["room_label"] == "304" and me["section_label"] == "North"

    await login("sup-e2e", "pw-123456")
    await client.post(f"/api/supervisor/stays/{st}/relocate",
                      json={"new_room_id": r2})
    await login(uname, "pw-123456")
    me = (await client.get("/api/auth/me")).json()
    assert me["room_label"] == "511" and me["section_label"] == "South"

    await login("sup-e2e", "pw-123456")
    await client.patch(f"/api/supervisor/rooms/{r2}",
                       json={"section_id": s1})
    await login(uname, "pw-123456")
    assert (await client.get("/api/auth/me")).json()["section_label"] \
        == "North"

    await login("sup-e2e", "pw-123456")
    await client.post(f"/api/supervisor/stays/{st}/checkout")
    await login(uname, "pw-123456")
    assert (await client.get("/api/auth/me")).json().get("room_id") is None

    await login("sup-e2e", "pw-123456")
    again = await client.post("/api/supervisor/stays", json={
        "guest_account_id": g, "room_id": r1,
        "check_in": "2026-06-01T14:00:00Z",
        "check_out": "2026-06-03T11:00:00Z"})
    assert again.status_code == 201
