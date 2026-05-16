# tests/binding/test_seed_property.py
from sqlalchemy import func, select
from conduit.shared.models.property import Property
from conduit.seed import ensure_property


async def test_ensure_property_idempotent(db):
    await ensure_property(db)
    await ensure_property(db)
    await db.commit()
    n = (await db.execute(
        select(func.count()).select_from(Property))).scalar_one()
    assert n == 1
