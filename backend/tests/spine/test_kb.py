async def test_kb_crud(client, make_account, login):
    await make_account("supervisor", "sup", "pw-123456")
    await login("sup", "pw-123456")
    r = await client.post("/api/supervisor/kb",
        json={"topic": "breakfast", "content": "7-10:30 in the Atrium"})
    assert r.status_code == 201
    kid = r.json()["id"]
    r2 = await client.post("/api/supervisor/kb",
        json={"topic": "x", "content": ""})
    assert r2.status_code == 422
    r3 = await client.patch(f"/api/supervisor/kb/{kid}",
        json={"status": "disabled"})
    assert r3.status_code == 200 and r3.json()["status"] == "disabled"
    r4 = await client.delete(f"/api/supervisor/kb/{kid}")
    assert r4.status_code == 405
