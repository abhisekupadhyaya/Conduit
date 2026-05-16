"""Child sub-request lifecycle — the state machine.

The child is the unit (D35); request is a thin container. Interruptible from
every state by the supervisor (D6) — modelled as a guarded transition, not a
special state. Closure is guest-final; no-dispatch uses closure-lite (D8).
Transitions and triggers are the commitment; node shapes stay soft (see
docs/datamodels/lifecycle.md).
"""
from __future__ import annotations

from enum import Enum


class ChildState(str, Enum):
    INTAKE = "intake"
    TRIAGED = "triaged"
    CLARIFYING = "clarifying"
    ROUTING = "routing"
    PUSHED = "pushed"
    BROADCAST = "broadcast"
    ACCEPTED = "accepted"
    IN_PROGRESS = "in_progress"
    DONE_PENDING_CONFIRM = "done_pending_confirm"
    ANSWERED = "answered"
    CONCIERGE_QUEUE = "concierge_queue"
    CLOSED = "closed"
    REOPENED = "reopened"
    CANCELLED = "cancelled"


def transition(child_id: str, to: ChildState) -> None:
    """Apply a guarded transition and append the corresponding event
    (conduit.shared.events) in the same transaction (AD5)."""
    raise NotImplementedError
