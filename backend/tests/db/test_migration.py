import pytest

pytestmark = pytest.mark.asyncio


async def test_account_constraints_enforced(db):
    from sqlalchemy import text
    # bad role rejected
    with pytest.raises(Exception):
        await db.execute(text(
            "insert into account(id,role,username,secret_hash,display_name)"
            " values (gen_random_uuid(),'wizard','u','h','U')"
        ))
        await db.flush()
    await db.rollback()
    # case-insensitive uniqueness
    from conduit.shared.models import Account
    db.add(Account(role="guest", username="Maria", secret_hash="h", display_name="M"))
    await db.flush()
    db.add(Account(role="guest", username="maria", secret_hash="h", display_name="M2"))
    with pytest.raises(Exception):
        await db.flush()
