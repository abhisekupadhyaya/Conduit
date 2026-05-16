"""Async SQLAlchemy engine + session + declarative base.

The durable state machine and timers live here — this is where the product's
"nothing is silently lost" promise physically lives (AD3/AD5), so the DB is
the one component never cost-optimised away.
"""
from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from conduit.core.config import get_settings


class Base(DeclarativeBase):
    """Declarative base for all ORM models (conduit.shared.models)."""


_settings = get_settings()
engine = create_async_engine(_settings.database_url, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency: a request-scoped async session."""
    async with SessionLocal() as session:
        yield session
