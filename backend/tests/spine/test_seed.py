import sqlalchemy as sa
from conduit.shared.models import IssueCode
from conduit.seed import ensure_issue_codes


async def test_seed_is_insert_missing_only(db):
    await ensure_issue_codes(db); await db.flush()
    n1 = len((await db.execute(sa.select(IssueCode))).scalars().all())
    # supervisor disables one
    one = (await db.execute(sa.select(IssueCode).limit(1))).scalars().first()
    one.status = "disabled"; db.add(one); await db.flush()
    await ensure_issue_codes(db); await db.flush()       # re-seed
    rows = (await db.execute(sa.select(IssueCode))).scalars().all()
    assert len(rows) == n1                                 # no dup
    again = await db.get(IssueCode, one.id)
    assert again.status == "disabled"                      # edit survived
