import pytest

pytestmark = pytest.mark.asyncio


async def test_dal_crud_and_case_insensitive(db):
    from conduit.public.dal import accounts as dal

    a = await dal.insert_account(db, role="guest", username="Maria",
                                 secret_hash="h", display_name="M")
    await db.flush()
    assert a.id is not None

    assert (await dal.get_by_username(db, "maria")).id == a.id   # ci hit
    assert await dal.get_by_username(db, "nope") is None
    assert (await dal.get_by_id(db, a.id)).username == "Maria"

    await dal.insert_account(db, role="supervisor", username="sup",
                             secret_hash="h", display_name="S")
    await db.flush()
    only_guests = await dal.list_accounts(db, role="guest")
    assert [x.username for x in only_guests] == ["Maria"]

    await dal.update_account(db, a, display_name="Maria R")
    await db.flush()
    assert (await dal.get_by_id(db, a.id)).display_name == "Maria R"

    assert await dal.count_active_by_role(db, "supervisor") == 1
