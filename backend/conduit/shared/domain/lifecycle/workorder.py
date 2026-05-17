"""Work order lifecycle machine — pure legal-transition matrix.

A WorkOrder is the dispatch leg of a child (D12/D18). PURE: no DB, no I/O,
no clock — effecting lives in the Phase C4 orchestrator. The state
vocabulary is exactly ck_wo_state (conduit.shared.models.work_order):
created, pushed, broadcast, accepted, in_progress, completed, cancelled.

Arc: created -> pushed|broadcast -> accepted -> in_progress -> completed.
Cancellable from any non-terminal state (supervisor interrupt, D6).
"""
from __future__ import annotations

_LEGAL: dict[str, set[str]] = {
    "created": {"pushed", "broadcast", "cancelled"},
    "pushed": {"accepted", "cancelled"},
    "broadcast": {"accepted", "cancelled"},
    "accepted": {"in_progress", "cancelled"},
    "in_progress": {"completed", "cancelled"},
}


def legal(frm: str, to: str) -> bool:
    return to in _LEGAL.get(frm, set())
