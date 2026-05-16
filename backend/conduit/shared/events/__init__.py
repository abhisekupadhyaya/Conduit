"""Append-only event log — the spine of observability.

Every state transition appends one event. Awareness stream, decision queue,
and analytics are read-models over this, never over the core tables. New event types are additive — this is the primary
evolution seam, so the vocabulary is an open string, not an enum.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Event:
    producer: str  # guest | servicer | supervisor | duty_manager | system
    subject_type: str  # child_sub_request | work_order | escalation | glitch | stay
    subject_id: str
    type: str  # open vocabulary
    payload: dict[str, Any]
    actor_id: str | None = None


async def record_event(session: Any, event: Event) -> None:
    """Persist one event. Implemented once the `event` model lands.

    Must be called inside the same transaction as the state transition it
    records, so the log can never disagree with state (AD5).
    """
    raise NotImplementedError("event model pending — see docs/datamodels")
