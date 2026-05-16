"""Test bench: a throwaway conduit_test DB built by alembic, function-scoped
model-delete teardown in a finally, an ASGI client bound to the test session,
and real-service factories. No sqlite — Postgres parity is required."""
from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from conduit.core.config import get_settings


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    return "asyncio"


def _admin_url() -> str:
    return get_settings().test_admin_url


def _test_url() -> str:
    s = get_settings()
    base = s.test_admin_url.rsplit("/", 1)[0]
    return f"{base}/{s.test_database_name}"


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _create_test_db() -> AsyncGenerator[None, None]:
    name = get_settings().test_database_name
    admin = create_async_engine(_admin_url(), isolation_level="AUTOCOMMIT")
    async with admin.connect() as c:
        await c.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        await c.execute(text(f'CREATE DATABASE "{name}"'))
    await admin.dispose()

    # Build schema via alembic against the test DB.
    import os
    from alembic import command
    from alembic.config import Config

    os.environ["CONDUIT_DATABASE_URL"] = _test_url()
    get_settings.cache_clear()  # type: ignore[attr-defined]
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", _test_url())
    command.upgrade(cfg, "head")

    yield

    admin = create_async_engine(_admin_url(), isolation_level="AUTOCOMMIT")
    async with admin.connect() as c:
        await c.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
    await admin.dispose()


@pytest_asyncio.fixture()
async def db() -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine(_test_url())
    Session = async_sessionmaker(engine, expire_on_commit=False)
    session = Session()
    try:
        yield session
    finally:
        # Explicit model-level delete (no inverse service exists — D29).
        from conduit.shared.models import Account
        await session.rollback()
        await session.execute(delete(Account))
        await session.commit()
        await session.close()
        await engine.dispose()


@pytest_asyncio.fixture()
async def client(db: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    from conduit.core.deps import db_session
    from conduit.main import app

    async def _override() -> AsyncGenerator[AsyncSession, None]:
        yield db

    app.dependency_overrides[db_session] = _override
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        yield c
    app.dependency_overrides.clear()


@pytest_asyncio.fixture()
async def make_account(db: AsyncSession):
    """Build precondition accounts through the REAL service path."""
    from conduit.supervisor.services import accounts as svc

    async def _make(role: str, username: str, password: str = "pw-123456",
                    display_name: str = "Test User"):
        acc = await svc.create_account(
            db, role=role, username=username,
            display_name=display_name, password=password)
        await db.commit()
        return acc

    return _make


@pytest_asyncio.fixture()
async def login(client: AsyncClient):
    async def _login(username: str, password: str):
        r = await client.post("/api/auth/login",
                              json={"username": username, "password": password})
        assert r.status_code == 200, r.text
        return r
    return _login
