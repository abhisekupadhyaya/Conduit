# conduit/servicer/services/presence.py
"""Servicer presence write — the off-shift 409 server lock + one event.

Spec §4 "Off-shift presence lock": a REAL server gate. If the servicer is
not on-shift at business ``now`` (``current_window is None``) the write is
rejected with ``ConflictError`` (409) — server-side regardless of client;
the UI lock is cosmetic.

§4 "Presence shift-scoping": we only store ``presence`` + ``presence_set_at
= clock.now()``; the pure Task-3 derivation does the scoping (a toggle counts
only while ``presence_set_at ∈ current_window``).

Events seam (§4): config mutations do NOT go through ``lifecycle.transition``;
they append to the merged ``shared/events`` log directly. The call shape
(``Event`` -> ``s.add`` -> ``await s.flush()`` -> typed detail row keyed by
``event_id`` -> trailing ``await s.flush()``) is byte-uniform with the
Task-5/6 supervisor services so the Task-8 append-only guard sees one
consistent pattern. Service flushes; the API handler commits at the edge.
"""
from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from conduit.core import clock
from conduit.core.deps import Actor
from conduit.core.exceptions import ConflictError
from conduit.servicer.dal import self as dal
from conduit.shared.domain import availability
from conduit.shared.models import Event, EventPresenceChanged


async def set_presence(s: AsyncSession, actor: Actor, presence: str) -> None:
    account_id = uuid.UUID(str(actor.id))
    assignments = await dal.get_assignments(s, account_id)
    now = clock.now()
    if availability.current_window(assignments, now) is None:
        raise ConflictError("off-shift: presence is locked")
    await dal.set_presence(s, account_id, presence, set_at=now)
    e = Event(type="presence_changed", actor_account_id=actor.id)
    s.add(e)
    await s.flush()
    s.add(EventPresenceChanged(event_id=e.id, account_id=account_id))
    await s.flush()
