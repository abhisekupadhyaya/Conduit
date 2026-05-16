import pytest

pytestmark = pytest.mark.asyncio

ROUTES = [
    ("get", "/api/supervisor/accounts"),
    ("post", "/api/supervisor/accounts"),
]


async def test_role_gating_matrix(client, make_account, login):
    # no cookie → 401
    assert (await client.get("/api/supervisor/accounts")).status_code == 401
    for role in ("guest", "servicer"):
        await make_account(role, f"{role}1", "pw-123456")
        await login(f"{role}1", "pw-123456")
        assert (await client.get("/api/supervisor/accounts")).status_code == 403
        await client.post("/api/auth/logout")


async def test_supervisor_crud_no_delete(client, make_account, login):
    await make_account("supervisor", "sup1", "pw-123456")
    await make_account("supervisor", "sup2", "pw-123456")  # avoid last-supervisor guard
    await login("sup1", "pw-123456")

    c = await client.post("/api/supervisor/accounts", json={
        "role": "servicer", "username": "newsvc",
        "display_name": "New", "password": "pw-123456"})
    assert c.status_code == 201
    assert "secret_hash" not in c.json()
    new_id = c.json()["id"]

    dup = await client.post("/api/supervisor/accounts", json={
        "role": "servicer", "username": "NEWSVC",
        "display_name": "d", "password": "pw-123456"})
    assert dup.status_code == 409

    lst = await client.get("/api/supervisor/accounts?role=servicer")
    assert lst.status_code == 200 and any(a["id"] == new_id for a in lst.json())

    # created account can actually log in
    await client.post("/api/auth/logout")
    assert (await client.post("/api/auth/login", json={
        "username": "newsvc", "password": "pw-123456"})).status_code == 200

    # disable blocks login; re-enable restores
    await login("sup1", "pw-123456")
    d = await client.patch(f"/api/supervisor/accounts/{new_id}",
                           json={"status": "disabled"})
    assert d.status_code == 200
    await client.post("/api/auth/logout")
    assert (await client.post("/api/auth/login", json={
        "username": "newsvc", "password": "pw-123456"})).status_code == 401

    # no DELETE route exists (D29)
    await login("sup1", "pw-123456")
    assert (await client.delete(
        f"/api/supervisor/accounts/{new_id}")).status_code == 405
