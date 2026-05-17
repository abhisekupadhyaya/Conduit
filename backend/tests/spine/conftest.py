"""Spine package test bench — savepoint-rollback isolation + FakeLLM.

This conftest OVERRIDES the merged root ``db`` fixture *for the tests/spine
package only* with the canonical SQLAlchemy 2.x "join an external transaction
with savepoint restart" recipe: a single outer transaction is opened on a
dedicated connection, the session runs inside a nested SAVEPOINT that is
restarted after every ``commit``/``rollback`` the application edge performs,
and at teardown the one outer transaction is rolled back ALWAYS — pass, fail,
or exception. Net effect: "pass ⇒ comfort, fail ⇒ rollback" — nothing a spine
test writes can persist or leak into the next test (proved by
``test_structural_guards.py::test_leak_sentinel``).

The root ``client``/``make_account``/``login`` fixtures depend on a fixture
named ``db``; this package-level override shadows the root one for spine tests
while staying drop-in compatible with those fixtures (``make_account`` still
commits — that commit now lands in the restarted savepoint and is rolled back
at teardown).
"""
from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy import event
from sqlalchemy.ext.asyncio import (AsyncSession, async_sessionmaker,
                                    create_async_engine)

from conduit.core.config import get_settings
from conduit.shared.integrations import openai as llm


def _test_url() -> str:
    """Test DB URL, built exactly the way the root conftest builds it."""
    s = get_settings()
    base = s.test_admin_url.rsplit("/", 1)[0]
    return f"{base}/{s.test_database_name}"


@pytest_asyncio.fixture()
async def db() -> AsyncGenerator[AsyncSession, None]:
    """Savepoint-rollback isolated session (overrides the merged root ``db``
    for this package only).

    A fresh engine is created PER TEST (mirroring the proven root conftest
    pattern — pytest-asyncio runs a function-scoped event loop, so a
    session-scoped async engine's pool would break across loops). The schema
    itself is already built once by the root session-autouse
    ``_create_test_db`` fixture (alembic upgrade head); this only connects.

    A single outer transaction is opened on a dedicated connection; the
    session runs inside a nested SAVEPOINT restarted after every
    commit/rollback the app edge performs; teardown rolls the one outer
    transaction back ALWAYS."""
    engine = create_async_engine(_test_url())
    conn = await engine.connect()
    trans = await conn.begin()
    Session = async_sessionmaker(bind=conn, expire_on_commit=False,
                                 class_=AsyncSession)
    s = Session()
    await conn.begin_nested()

    @event.listens_for(s.sync_session, "after_transaction_end")
    def _restart(sess, transaction):
        # Restart the SAVEPOINT whenever the inner nested transaction ends
        # (the app edge's commit/rollback) so subsequent writes stay inside a
        # savepoint that the single outer ``trans.rollback()`` discards.
        if transaction.nested and not transaction._parent.nested:
            sess.begin_nested()

    # Reset the module-level LLM circuit breaker so tripped-breaker state from
    # an earlier spine test cannot leak into this one.
    llm._reset_circuit_breaker()
    try:
        yield s
    finally:
        await s.close()
        await trans.rollback()          # rollback ALWAYS (pass/fail/error)
        await conn.close()
        await engine.dispose()
        llm._reset_circuit_breaker()


@pytest.fixture()
def fake_llm(monkeypatch):
    """Deterministic LLM double. Set ``state["classify"]``/``state["ground"]``
    to async callables in the test; the wrappers await them, mirroring the
    fakes in test_triage.py / test_intake_service.py."""
    state = {"classify": None, "ground": None}

    async def c(t, cat, history: str = ""):
        return await state["classify"](t, cat)

    async def g(q, ctx, history: str = ""):
        return await state["ground"](q, ctx)

    monkeypatch.setattr(llm, "classify", c)
    monkeypatch.setattr(llm, "ground", g)
    return state


@pytest.fixture()
def monkeypatch_all(monkeypatch):
    """Provide ``monkeypatch_all`` as the callable the unskipped intake test
    invokes by bare name: ``monkeypatch_all(llm, fclassify, fground)``. It
    swaps in the test's async ``fclassify``/``fground`` as
    ``llm.classify``/``llm.ground``; monkeypatch reverts the swap at teardown.
    This is the conftest-provided helper Step 5 calls for; receiving it is the
    only test-signature change to the otherwise-verbatim intake test."""

    def _apply(llm_mod, fclassify, fground):
        monkeypatch.setattr(llm_mod, "classify", fclassify)
        monkeypatch.setattr(llm_mod, "ground", fground)

    return _apply


@pytest_asyncio.fixture()
async def seeded_guest_with_stay(db, make_account):
    """Real FK-chain precondition (same proven arrange as
    tests/spine/test_guest_dal.py::_chain): a guest Account with an ACTIVE
    Stay in a Room/Section/Property, so
    ``bindings.get_active_binding_for_guest`` resolves and
    ``intake.submit_request`` does not 409.

    ``make_account`` (which commits) runs FIRST; the chain is flushed (NOT
    committed) so the single outer savepoint rollback discards it. Returns
    ``(actor, ambient)`` where ``actor`` is the guest Account (it has ``.id``,
    exactly what the intake service consumes) and ``ambient`` mirrors the
    intake service's ambient dict."""
    from conduit.shared.models import Property, Room, Section, Stay

    acc = await make_account("guest", f"g-{uuid.uuid4().hex[:8]}")
    p = Property(name="T")
    db.add(p)
    await db.flush()
    sec = Section(property_id=p.id, label="S")
    db.add(sec)
    await db.flush()
    room = Room(section_id=sec.id, label="R")
    db.add(room)
    await db.flush()
    now = dt.datetime.now(dt.timezone.utc)
    stay = Stay(guest_account_id=acc.id, room_id=room.id,
                check_in=now, check_out=now + dt.timedelta(days=1),
                status="active")
    db.add(stay)
    await db.flush()
    ambient = {"room_label": room.label, "section_label": sec.label,
               "check_in": stay.check_in, "check_out": stay.check_out,
               "stay_status": stay.status}
    return acc, ambient


@pytest_asyncio.fixture()
async def make_child(make_account):
    """Async callable building the minimal valid FK chain
    Property→Section→Room→Account→Stay→Request→ChildSubRequest via the real
    models (same proven arrange as test_lifecycle.py / test_migration.py).
    Returns the created ``ChildSubRequest``.

    ``make_account`` (which commits) runs FIRST; the rest of the chain is
    flushed (NOT committed) so the single outer savepoint rollback discards
    it. Takes ``db`` as an argument (mirroring the test signatures) so it
    binds to the same savepoint-isolated session the test uses."""
    from conduit.shared.models import (ChildSubRequest, Property, Request,
                                       Room, Section, Stay)

    async def _make(db):
        acc = await make_account("guest", f"g-{uuid.uuid4().hex[:8]}")
        p = Property(name="T")
        db.add(p)
        await db.flush()
        sec = Section(property_id=p.id, label="S")
        db.add(sec)
        await db.flush()
        room = Room(section_id=sec.id, label="R")
        db.add(room)
        await db.flush()
        now = dt.datetime.now(dt.timezone.utc)
        stay = Stay(guest_account_id=acc.id, room_id=room.id,
                    check_in=now, check_out=now + dt.timedelta(days=1),
                    status="active")
        db.add(stay)
        await db.flush()
        r = Request(guest_account_id=acc.id, stay_id=stay.id, raw_text="x")
        db.add(r)
        await db.flush()
        c = ChildSubRequest(request_id=r.id, text="x", outcome="no_dispatch",
                            state="intake")
        db.add(c)
        await db.flush()
        return c

    return _make


@pytest.fixture(autouse=True)
def _leak_sentinel():
    """Fallback that must never fire: savepoint rollback already guarantees a
    clean baseline between tests. Its presence documents the invariant; the
    actual assertion lives in
    test_structural_guards.py::test_leak_sentinel (a fresh-session check)."""
    yield
