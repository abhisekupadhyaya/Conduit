"""Child sub-request lifecycle machine — pure legal-transition matrix.

The child is the unit (D35); request is a thin container. Interruptible from
every state by the supervisor (D6) — modelled as a guarded ``->cancelled``
transition, not a special state. Closure is guest-final; no-dispatch uses
closure-lite (D8). Transitions are the commitment; node shapes stay soft
(see docs/datamodels/lifecycle.md).

PURE: no DB, no I/O, no clock. Effecting (set state, emit events, arm timers)
lives in the Phase C4 lifecycle orchestrator, never here. The state
vocabulary is exactly ck_child_state (conduit.shared.models.child_sub_request).
``ChildState`` is the canonical enum, moved here from the pre-package
``lifecycle.py``; the package ``__init__`` re-exports it for back-compat.
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


# The merged ``lifecycle.py`` _LEGAL (preserved, additive — these transitions
# stay legal so existing no-dispatch/smalltalk/intake consumers are unaffected):
#   intake -> triaged
#   triaged -> answered | concierge_queue
#   answered -> closed | reopened
#   reopened -> concierge_queue
# unioned with the A5-widened dispatch arc:
#   triaged -> routing
#   routing -> pushed | broadcast
#   pushed | broadcast -> accepted
#   accepted -> in_progress
#   in_progress -> done_pending_confirm
#   done_pending_confirm -> closed | reopened
# plus the supervisor interrupt (D6): any active state -> cancelled.
_LEGAL: dict[str, set[str]] = {
    "intake": {"triaged"},
    "triaged": {"answered", "concierge_queue", "routing", "cancelled"},
    "clarifying": {"triaged", "cancelled"},
    "routing": {"pushed", "broadcast", "cancelled"},
    "pushed": {"accepted", "cancelled"},
    "broadcast": {"accepted", "cancelled"},
    "accepted": {"in_progress", "cancelled"},
    "in_progress": {"done_pending_confirm", "cancelled"},
    "done_pending_confirm": {"closed", "reopened", "cancelled"},
    "answered": {"closed", "reopened"},
    "concierge_queue": {"cancelled"},
    "reopened": {"concierge_queue"},
}


def legal(frm: str, to: str) -> bool:
    return to in _LEGAL.get(frm, set())
