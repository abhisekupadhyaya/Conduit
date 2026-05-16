"""Triage mechanism — cross-portal domain logic (not a portal slice).

Triggered from guest intake (conduit.guest.services.intake) but the mechanism
is shared and portal-agnostic. Mechanical, not vibe-based (D5/D30):
slot-completeness + a deterministic objective risk rulebook; the LLM may only
*raise* a rule-defined risk, never infer one from tone.

Pipeline (D35 → D5): decompose → per-child classify → per-child triage.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class TriageOutcome(str, Enum):
    AUTO = "auto"
    CLARIFY = "clarify"
    FLAG = "flag"
    NO_DISPATCH = "no_dispatch"


@dataclass
class TriagedChild:
    text: str
    issue_code: str | None
    outcome: TriageOutcome
    uncategorized: bool = False
    is_problem_report: bool = False  # D43 → opens a Glitch


def decompose(raw_text: str) -> list[str]:
    """One guest message → N independent child texts (D35).

    >1 ⇒ caller echoes the split back (D36). LLM-assisted; failure must fall
    into a conservative path, never silently drop items (AD11).
    """
    raise NotImplementedError


def classify(child_text: str) -> str | None:
    """Map a child to an issue code (D34). None ⇒ uncategorized → clarify/flag."""
    raise NotImplementedError


def triage(child_text: str) -> TriagedChild:
    """Slot-completeness + deterministic risk rulebook → outcome (D5/D30).

    Reservation/revenue mutations always FLAG, never AUTO (D24).
    Priority tier is derived from the issue code's SLA preset and is
    independent of this outcome (D20) — never from guest-asserted urgency.
    """
    raise NotImplementedError
