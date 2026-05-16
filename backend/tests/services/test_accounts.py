import pytest

pytestmark = pytest.mark.asyncio


async def test_create_hashes_and_rejects_dupe_and_bad_role(db):
    from conduit.supervisor.services import accounts as svc
    from conduit.core.exceptions import ConflictError, ConduitError
    from conduit.core.security import verify_password

    a = await svc.create_account(db, role="servicer", username="svc1",
                                 display_name="S", password="pw-123456")
    await db.flush()
    assert a.secret_hash != "pw-123456"
    assert verify_password("pw-123456", a.secret_hash)

    with pytest.raises(ConflictError):
        await svc.create_account(db, role="servicer", username="SVC1",
                                 display_name="dup", password="pw-123456")
    with pytest.raises(ConduitError):
        await svc.create_account(db, role="wizard", username="w",
                                 display_name="w", password="pw-123456")


async def test_update_lockout_guards(db):
    from conduit.supervisor.services import accounts as svc
    from conduit.core.exceptions import ConflictError
    from conduit.core.deps import Actor

    sup = await svc.create_account(db, role="supervisor", username="sup1",
                                   display_name="S", password="pw-123456")
    await db.flush()
    actor = Actor(id=str(sup.id), role="supervisor")

    # cannot disable self
    with pytest.raises(ConflictError):
        await svc.update_account(db, actor, sup.id, {"status": "disabled"})
    # cannot disable the last active supervisor (a different actor)
    other = Actor(id="00000000-0000-0000-0000-000000000000", role="supervisor")
    with pytest.raises(ConflictError):
        await svc.update_account(db, other, sup.id, {"status": "disabled"})

    sup2 = await svc.create_account(db, role="supervisor", username="sup2",
                                    display_name="S2", password="pw-123456")
    await db.flush()
    # now sup1 is not the last → disabling is allowed
    await svc.update_account(db, other, sup2.id, {"status": "disabled"})
    await db.flush()
    assert sup2.status == "disabled"
