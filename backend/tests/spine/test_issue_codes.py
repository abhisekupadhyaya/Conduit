async def _sup(make_account, login):
    await make_account("supervisor", "sup", "pw-123456")
    await login("sup", "pw-123456")


async def test_crud_and_mutation_lock(client, make_account, login):
    await _sup(make_account, login)
    r = await client.post("/api/supervisor/issue-codes", json={
        "code": "INFO_DINING", "label": "Dining info", "department": "concierge",
        "fulfilment_mode": "no_dispatch", "routing_model": "none",
        "intent_kind": "service"})
    assert r.status_code == 201
    body = r.json()
    assert body["is_reservation_mutation"] is False        # display present
    # Resolution A: request schema rejects the locked field
    r2 = await client.post("/api/supervisor/issue-codes", json={
        "code": "X", "label": "x", "department": "d",
        "fulfilment_mode": "no_dispatch", "routing_model": "none",
        "intent_kind": "service", "is_reservation_mutation": True})
    assert r2.status_code == 422
    # duplicate code (case-insensitive)
    r3 = await client.post("/api/supervisor/issue-codes", json={
        "code": "info_dining", "label": "dup", "department": "d",
        "fulfilment_mode": "no_dispatch", "routing_model": "none",
        "intent_kind": "service"})
    assert r3.status_code == 409
    # patch + disable
    cid = body["id"]
    r4 = await client.patch(f"/api/supervisor/issue-codes/{cid}",
                            json={"status": "disabled"})
    assert r4.status_code == 200 and r4.json()["status"] == "disabled"
    # bad enum
    r5 = await client.patch(f"/api/supervisor/issue-codes/{cid}",
                            json={"fulfilment_mode": "bogus"})
    assert r5.status_code == 422
    # no DELETE
    r6 = await client.delete(f"/api/supervisor/issue-codes/{cid}")
    assert r6.status_code == 405


async def test_requires_supervisor(client):
    r = await client.get("/api/supervisor/issue-codes")
    assert r.status_code in (401, 403)
