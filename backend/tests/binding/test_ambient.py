# tests/binding/test_ambient.py
from datetime import datetime, timedelta, timezone
from conduit.supervisor.services import sections as ssvc, rooms as rsvc, stays as stsvc


async def test_me_carries_ambient_no_relogin(
    db, client, make_account, login, seeded_property,
):
    await make_account("supervisor", "sup-a", "pw-123456")
    g = await make_account("guest", "guest-a", "pw-123456")
    sec = await ssvc.create_section(db, seeded_property.id, "North",
                                    actor=None)
    await db.flush()
    r1 = await rsvc.create_room(db, "304", sec.id, actor=None)
    sec2 = await ssvc.create_section(db, seeded_property.id, "South",
                                     actor=None)
    await db.flush()
    r2 = await rsvc.create_room(db, "511", sec2.id, actor=None)
    await db.flush()
    n = datetime.now(timezone.utc)
    st = await stsvc.create_stay(db, g.id, r1.id, n, n + timedelta(days=1),
                                 actor=None)
    await db.commit()

    await login("guest-a", "pw-123456")
    me = (await client.get("/api/auth/me")).json()
    assert me["room_label"] == "304" and me["section_label"] == "North"

    await stsvc.relocate_stay(db, st.id, r2.id, actor=None)
    await db.commit()
    me2 = (await client.get("/api/auth/me")).json()  # same cookie, no re-login
    assert me2["room_label"] == "511" and me2["section_label"] == "South"


async def test_me_ambient_null_for_supervisor(client, make_account, login):
    await make_account("supervisor", "sup-b", "pw-123456")
    await login("sup-b", "pw-123456")
    me = (await client.get("/api/auth/me")).json()
    assert me.get("room_id") is None
