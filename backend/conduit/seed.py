"""Idempotent bootstrap-supervisor seed: python -m conduit.seed.
Fail-fast on missing creds (never a silent no-op)."""
from __future__ import annotations

import asyncio
import sys

from sqlalchemy.ext.asyncio import AsyncSession

from conduit.core.config import get_settings
from conduit.public.dal import accounts as dal
from conduit.shared.db import SessionLocal
from conduit.supervisor.services import accounts as svc


from sqlalchemy import select as _select
from conduit.shared.models.property import Property as _Property


async def ensure_property(s, name: str = "Conduit Property") -> _Property:
    existing = (await s.execute(_select(_Property))).scalars().first()
    if existing is not None:
        return existing
    p = _Property(name=name)
    s.add(p)
    await s.flush()
    return p


async def run(s: AsyncSession, *, username: str, password: str) -> None:
    if not username or not password:
        print("seed: CONDUIT_SEED_SUPERVISOR_USERNAME/PASSWORD required",
              file=sys.stderr)
        raise SystemExit(2)
    if await dal.get_by_username(s, username) is not None:
        print(f"seed: supervisor '{username}' already exists; nothing to do")
        return
    await svc.create_account(s, role="supervisor", username=username,
                             display_name=username, password=password)
    print(f"seed: created supervisor '{username}'")


async def _main() -> None:
    st = get_settings()
    async with SessionLocal() as s:
        await ensure_property(s)
        await run(s, username=st.seed_supervisor_username,
                  password=st.seed_supervisor_password)
        await s.commit()


if __name__ == "__main__":
    asyncio.run(_main())
