"""Alembic environment — async, URL + metadata from the app (single source).

Models are deliberately not defined yet (the data model is "subject to
change"); `target_metadata` is Base.metadata so autogenerate works the moment
the first models land in conduit.shared.models.
"""
from __future__ import annotations

import asyncio

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

from conduit.core.config import get_settings
from conduit.shared.db import Base
from conduit.shared import models  # noqa: F401 — register models on import

target_metadata = Base.metadata
_db_url = get_settings().database_url


def run_migrations_offline() -> None:
    context.configure(
        url=_db_url, target_metadata=target_metadata, literal_binds=True
    )
    with context.begin_transaction():
        context.run_migrations()


def _do_run(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    engine = create_async_engine(_db_url)
    async with engine.connect() as conn:
        await conn.run_sync(_do_run)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
