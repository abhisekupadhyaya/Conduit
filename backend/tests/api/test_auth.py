import pytest

pytestmark = pytest.mark.asyncio


async def test_login_me_logout_cycle(client, make_account):
    await make_account("supervisor", "sup1", "pw-123456", "Sue")

    r = await client.post("/api/auth/login",
                          json={"username": "sup1", "password": "pw-123456"})
    assert r.status_code == 200
    body = r.json()
    assert body["role"] == "supervisor" and body["display_name"] == "Sue"
    sc = r.headers["set-cookie"]
    assert "conduit_session=" in sc and "HttpOnly" in sc
    assert "Secure" not in sc  # cookie_secure False in tests

    me = await client.get("/api/auth/me")
    assert me.status_code == 200 and me.json()["username"] == "sup1"

    out = await client.post("/api/auth/logout")
    assert out.status_code == 204
    assert (await client.get("/api/auth/me")).status_code == 401


async def test_login_failures_are_identical_and_setno_cookie(client, make_account):
    await make_account("guest", "g1", "pw-123456")
    a = await client.post("/api/auth/login",
                          json={"username": "g1", "password": "bad"})
    b = await client.post("/api/auth/login",
                          json={"username": "ghost", "password": "pw-123456"})
    assert a.status_code == b.status_code == 401
    assert a.json() == b.json()
    assert "set-cookie" not in a.headers


async def test_patch_me_changes_password(client, make_account, login):
    await make_account("guest", "g2", "old-123456", "Gee")
    await login("g2", "old-123456")
    r = await client.patch("/api/auth/me", json={
        "display_name": "Gee Two",
        "current_password": "old-123456", "new_password": "new-123456"})
    assert r.status_code == 200 and r.json()["display_name"] == "Gee Two"
    await client.post("/api/auth/logout")
    bad = await client.post("/api/auth/login",
                            json={"username": "g2", "password": "old-123456"})
    good = await client.post("/api/auth/login",
                             json={"username": "g2", "password": "new-123456"})
    assert bad.status_code == 401 and good.status_code == 200
