async def test_requires_guest(client):
    r = await client.post("/api/guest/requests", json={"text": "hi"})
    assert r.status_code in (401, 403)


async def test_no_active_stay_409(client, make_account, login):
    await make_account("guest", "g", "pw-123456")
    await login("g", "pw-123456")
    r = await client.post("/api/guest/requests", json={"text": "hi"})
    assert r.status_code == 409
