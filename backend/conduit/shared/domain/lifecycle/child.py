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
#
# §7.2 dispatch-leg carry (additive — NO edge removed): the dispatch child
# HOLDS at ``routing`` while the WorkOrder carries the visible leg
# (pushed→accepted→in_progress→completed; the guest card surfaces WO state —
# E1 design, accepted in review). No production code advances the child past
# ``routing``. On ``WorkOrder → completed`` the §7.2 C4 ``_workorder_hops``
# carry resumes the child's own arc at ``done_pending_confirm`` — Spec §7.2:
# "WorkOrder → completed ⇒ child → done_pending_confirm" (NOT conditional on
# the child being in_progress). The child machine therefore must legally allow
# the dispatch-leg holding state → ``done_pending_confirm``. We additively add
# ``routing -> done_pending_confirm`` (the actual holding state) and, for
# robustness/consistency regardless of which dispatch-leg state the child
# happens to hold when the WO completes, also ``pushed``/``broadcast``/
# ``accepted`` -> ``done_pending_confirm`` (``in_progress -> ...`` already
# exists). This is PURELY ADDITIVE: every pre-existing edge below is retained
# unchanged (C3 superset/back-compat + the legacy ``test_lifecycle.py`` arc
# stay green; ``*->cancelled`` and the legacy edges are intact).
_LEGAL: dict[str, set[str]] = {
    "intake": {"triaged"},
    "triaged": {"answered", "concierge_queue", "routing", "cancelled"},
    "clarifying": {"triaged", "cancelled"},
    "routing": {"pushed", "broadcast", "done_pending_confirm", "cancelled"},
    "pushed": {"accepted", "done_pending_confirm", "cancelled"},
    "broadcast": {"accepted", "done_pending_confirm", "cancelled"},
    "accepted": {"in_progress", "done_pending_confirm", "cancelled"},
    "in_progress": {"done_pending_confirm", "cancelled"},
    "done_pending_confirm": {"closed", "reopened", "cancelled"},
    "answered": {"closed", "reopened"},
    "concierge_queue": {"cancelled"},
    "reopened": {"concierge_queue"},
}


def legal(frm: str, to: str) -> bool:
    return to in _LEGAL.get(frm, set())
