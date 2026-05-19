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


from sqlalchemy import func as _func
from sqlalchemy import select as _select
from conduit.shared.models import IssueCode as _IssueCode
from conduit.shared.models.property import Property as _Property


async def ensure_property(s, name: str = "Conduit Property") -> _Property:
    existing = (await s.execute(_select(_Property))).scalars().first()
    if existing is not None:
        return existing
    p = _Property(name=name)
    s.add(p)
    await s.flush()
    return p


_DEFAULT_ISSUE_CODES = [
    dict(code="INFO_GENERAL", label="General info", department="concierge",
         fulfilment_mode="no_dispatch", routing_model="none",
         intent_kind="service", is_reservation_mutation=False),
    dict(code="INFO_DINING", label="Dining & hours", department="concierge",
         fulfilment_mode="no_dispatch", routing_model="none",
         intent_kind="service", is_reservation_mutation=False),
    dict(code="INFO_AMENITIES", label="Amenities & wifi",
         department="concierge", fulfilment_mode="no_dispatch",
         routing_model="none", intent_kind="service",
         is_reservation_mutation=False),
    dict(code="RES_MUTATION", label="Reservation change",
         department="front_office", fulfilment_mode="no_dispatch",
         routing_model="none", intent_kind="service",
         is_reservation_mutation=True),
    dict(code="HK_REQUEST", label="Housekeeping request",
         department="housekeeping", fulfilment_mode="dispatch",
         routing_model="section_pooled", intent_kind="service",
         is_reservation_mutation=False),
    dict(code="SMALLTALK", label="Casual conversation",
         department="concierge", fulfilment_mode="no_dispatch",
         routing_model="none", intent_kind="service",
         is_reservation_mutation=False),
    dict(code="FO-GUEST-MOVE", label="Guest move",
         department="front_office", fulfilment_mode="dispatch",
         routing_model="section_pooled", intent_kind="service",
         is_reservation_mutation=False, origin="system"),
]


async def ensure_issue_codes(db) -> None:
    for spec in _DEFAULT_ISSUE_CODES:
        exists = (await db.execute(_select(_IssueCode).where(
            _func.lower(_IssueCode.code) == spec["code"].lower()))
        ).scalars().first()
        if exists is None:
            db.add(_IssueCode(**spec))     # insert-missing only; never update


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
        await ensure_issue_codes(s)
        await run(s, username=st.seed_supervisor_username,
                  password=st.seed_supervisor_password)
        await s.commit()


if __name__ == "__main__":
    asyncio.run(_main())
