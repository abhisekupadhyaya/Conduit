# tests/binding/test_migration.py
from sqlalchemy import inspect, text


async def test_tables_and_partial_index_exist(db):
    def _names(c):
        return set(inspect(c.connection()).get_table_names())
    names = await db.run_sync(lambda c: _names(c))
    assert {"property", "section", "room", "stay", "event",
            "event_stay_created", "event_stay_ended",
            "event_guest_relocated"} <= names
    idx = (await db.execute(text(
        "select indexname from pg_indexes where tablename='stay'"
    ))).scalars().all()
    assert "uq_stay_one_active_per_guest" in idx
