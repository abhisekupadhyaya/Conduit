"""Glitch lifecycle machine — pure legal-transition matrix.

A Glitch opens from a problem_report or dispute (D-series glitch handling).
PURE: no DB, no I/O, no clock — effecting lives in the Phase C4
orchestrator. The state vocabulary is exactly ck_glitch_state
(conduit.shared.models.glitch): open, held_open, auto_closed, closed.

``open`` may be held_open, auto_closed, or closed; a held_open glitch can
still close. Terminal closures do not transition further.
"""
from __future__ import annotations

_LEGAL: dict[str, set[str]] = {
    "open": {"held_open", "auto_closed", "closed"},
    "held_open": {"closed", "auto_closed"},
}


def legal(frm: str, to: str) -> bool:
    return to in _LEGAL.get(frm, set())
