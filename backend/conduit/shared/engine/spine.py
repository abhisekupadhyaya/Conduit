"""The escalation spine (D9/D10/D20/D21).

Three triggers produce an AI recommendation for the supervisor decision
queue: triage-flag (D5/D24), stall (D10/D23), servicer-raised mid-lifecycle
escalation (D20). The supervisor approves/edits/overrides; silence past the
supervisor-SLA → AI auto-proceeds (D9). Bounded: after N cycles → hard-escalate
to the non-time-boxed duty manager (D21). The human never gets a blank ticket
(D7).
"""
from __future__ import annotations

from enum import Enum


class EscalationTrigger(str, Enum):
    TRIAGE_FLAG = "triage_flag"
    STALL = "stall"
    SERVICER_RAISED = "servicer_raised"


def open_escalation(child_id: str, trigger: EscalationTrigger) -> None:
    """Open a decision-queue item with an AI-prepared recommendation."""
    raise NotImplementedError


def auto_proceed(escalation_id: str) -> None:
    """Supervisor silent past SLA → proceed on the recommendation (D9),
    unless the D21 bound is hit → hard-escalate the duty manager."""
    raise NotImplementedError
