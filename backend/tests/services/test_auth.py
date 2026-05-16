import pytest

pytestmark = pytest.mark.asyncio


async def test_authenticate_paths(db, make_account):
    from conduit.public.services import auth
    from conduit.core.exceptions import AuthError

    await make_account("servicer", "svc1", "pw-123456")

    acc = await auth.authenticate(db, "svc1", "pw-123456")
    assert acc.username == "svc1"

    for u, p in [("svc1", "wrong"), ("ghost", "pw-123456")]:
        with pytest.raises(AuthError) as ei:
            await auth.authenticate(db, u, p)
        assert str(ei.value) == "invalid username or password"  # no enumeration

    await auth.update_self(db, acc, status_change=None, display_name=None,
                           current_password=None, new_password=None)  # no-op ok

    # disabled account cannot authenticate even with the right password
    from conduit.supervisor.services import accounts as svc
    from conduit.core.deps import Actor
    sup = await svc.create_account(db, role="supervisor", username="s9",
                                   display_name="S", password="pw-123456")
    await svc.create_account(db, role="supervisor", username="s10",
                             display_name="S", password="pw-123456")
    await db.flush()
    await svc.update_account(db, Actor(id="x", role="supervisor"), sup.id,
                             {"status": "disabled"})
    await db.flush()
    with pytest.raises(AuthError):
        await auth.authenticate(db, "s9", "pw-123456")


async def test_update_self_password(db, make_account):
    from conduit.public.services import auth
    from conduit.core.exceptions import AuthError
    from conduit.core.security import verify_password

    acc = await make_account("guest", "g1", "old-123456")
    with pytest.raises(AuthError):
        await auth.update_self(db, acc, status_change=None, display_name=None,
                               current_password="bad", new_password="new-123456")
    await auth.update_self(db, acc, status_change=None, display_name="Gee",
                           current_password="old-123456", new_password="new-123456")
    await db.flush()
    assert acc.display_name == "Gee"
    assert verify_password("new-123456", acc.secret_hash)
