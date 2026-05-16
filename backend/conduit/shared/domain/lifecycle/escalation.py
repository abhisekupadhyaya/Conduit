"""Escalation lifecycle machine — pure legal-transition matrix.

An Escalation opens on a trigger (triage_flag / stall / servicer_raised, D20)
and resolves once. PURE: no DB, no I/O, no clock — effecting lives in the
Phase C4 orchestrator. The state vocabulary is exactly ck_esc_state
(conduit.shared.models.escalation): open, approved, edited, overridden,
auto_proceeded, hard_escalated.

``open`` resolves into exactly one terminal disposition; terminal states do
not transition further (resolve-once).
"""
from __future__ import annotations

_LEGAL: dict[str, set[str]] = {
    "open": {
        "approved",
        "edited",
        "overridden",
        "auto_proceeded",
        "hard_escalated",
    },
}


def legal(frm: str, to: str) -> bool:
    return to in _LEGAL.get(frm, set())
