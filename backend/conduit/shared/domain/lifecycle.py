"""Child sub-request lifecycle — the state machine.

The child is the unit (D35); request is a thin container. Interruptible from
every state by the supervisor (D6) — modelled as a guarded transition, not a
special state. Closure is guest-final; no-dispatch uses closure-lite (D8).
Transitions and triggers are the commitment; node shapes stay soft (see
docs/datamodels/lifecycle.md).
"""
from __future__ import annotations

from enum import Enum

from sqlalchemy.ext.asyncio import AsyncSession

from conduit.core.exceptions import ConflictError
from conduit.shared.events import writer


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


_LEGAL = {
    "intake": {"triaged"},
    "triaged": {"answered", "concierge_queue"},
    "answered": {"closed", "reopened"},
    "reopened": {"concierge_queue"},
}
_EVENT = {
    "triaged": "child_triaged",
    "answered": "child_answered",
    "concierge_queue": "child_deferred",
    "closed": "child_closed",
    "reopened": "child_reopened",
}


async def transition(s: AsyncSession, child, to: str, *,
                     actor_account_id=None, resolution_child_id=None) -> None:
    """Apply a guarded transition and append the corresponding event
    (conduit.shared.events) in the same transaction (AD5)."""
    if to not in _LEGAL.get(child.state, set()):
        raise ConflictError(f"illegal transition {child.state}->{to}")
    child.state = to
    s.add(child)
    await writer.emit_child(s, _EVENT[to], child.id, actor_account_id,
                            resolution_child_id=resolution_child_id)
