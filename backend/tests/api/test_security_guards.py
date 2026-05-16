import json
import pathlib

import pytest

pytestmark = pytest.mark.asyncio

PUBLIC = {"/api/health", "/api/auth/login"}
SNAP = pathlib.Path(__file__).parent / "contract_snapshot.json"


def _routes():
    from conduit.main import app
    out = []
    for r in app.routes:
        path = getattr(r, "path", None)
        methods = getattr(r, "methods", None)
        if not path or not path.startswith("/api") or not methods:
            continue
        for m in sorted(methods):
            if m in ("HEAD", "OPTIONS"):
                continue
            out.append((m, path))
    return sorted(set(out))


async def test_no_endpoint_is_unauthenticated_by_accident(client):
    for method, path in _routes():
        if path in PUBLIC or "{" in path:
            continue
        resp = await client.request(method, path.replace("/api", "/api"))
        assert resp.status_code in (401, 403), f"{method} {path} -> {resp.status_code}"


def test_contract_snapshot_matches():
    current = _routes()
    if not SNAP.exists():
        SNAP.write_text(json.dumps(current, indent=2))
        pytest.skip("snapshot created; re-run to enforce")
    saved = json.loads(SNAP.read_text())
    assert [tuple(x) for x in saved] == current, (
        "API surface changed. If intentional, delete "
        f"{SNAP} and re-run to regenerate.")


async def test_secret_hash_never_serialized(client, make_account, login):
    await make_account("supervisor", "sup1", "pw-123456")
    await make_account("supervisor", "sup2", "pw-123456")
    await login("sup1", "pw-123456")
    bodies = []
    bodies.append((await client.get("/api/auth/me")).text)
    bodies.append((await client.get("/api/supervisor/accounts")).text)
    c = await client.post("/api/supervisor/accounts", json={
        "role": "guest", "username": "g9", "display_name": "G",
        "password": "pw-123456"})
    bodies.append(c.text)
    for b in bodies:
        assert "secret_hash" not in b


async def test_jwt_tamper_and_alg_none_rejected(client, make_account, login):
    import jwt
    await make_account("guest", "g1", "pw-123456")
    await login("g1", "pw-123456")
    # tampered secret
    bad = jwt.encode({"sub": "x", "role": "supervisor"}, "not-the-secret",
                     algorithm="HS256")
    client.cookies.set("conduit_session", bad)
    assert (await client.get("/api/auth/me")).status_code == 401
    # alg none
    none_tok = jwt.encode({"sub": "x", "role": "guest"}, key=None,
                          algorithm="none")
    client.cookies.set("conduit_session", none_tok)
    assert (await client.get("/api/auth/me")).status_code == 401
