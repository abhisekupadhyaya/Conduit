import pytest

pytestmark = pytest.mark.asyncio


async def test_seed_is_idempotent_and_creates_supervisor(db, monkeypatch):
    from conduit import seed
    from conduit.public.dal import accounts as dal

    await seed.run(db, username="boss", password="pw-123456")
    await db.commit()
    await seed.run(db, username="boss", password="pw-123456")  # idempotent
    await db.commit()

    sups = await dal.list_accounts(db, role="supervisor")
    assert [s.username for s in sups] == ["boss"]


async def test_seed_missing_env_fails_fast(db):
    from conduit import seed
    with pytest.raises(SystemExit):
        await seed.run(db, username="", password="")
