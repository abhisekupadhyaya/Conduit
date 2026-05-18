"""Triage mechanism — cross-portal domain logic (not a portal slice).

Triggered from guest intake (conduit.guest.services.intake) but the mechanism
is shared and portal-agnostic. Mechanical, not vibe-based (D5/D30):
slot-completeness + a deterministic objective risk rulebook; the LLM may only
*raise* a rule-defined risk, never infer one from tone.

Pipeline (D35 → D5): decompose → per-child classify → per-child triage.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from enum import Enum

from conduit.shared.integrations import openai as llm


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
    requested_checkout: "dt.datetime | None" = None  # D24 extracted target


async def decompose(raw_text: str) -> list[str]:
    """One guest message → N independent child texts (D35).

    >1 ⇒ caller echoes the split back (D36). LLM-assisted; any failure or an
    empty result falls back to the single original text — never 0, never a
    silent drop (AD11)."""
    try:
        texts = await llm.decompose(raw_text)
    except llm.LLMUnavailable:
        return [raw_text]
    cleaned = [t.strip() for t in (texts or []) if t and t.strip()]
    return cleaned or [raw_text]


async def classify(text: str, catalog: list[dict],
                   history: str = "") -> list[TriagedChild]:
    """Decompose + classify a guest message (D34/D35), then apply the
    deterministic risk pass (D24/D30, Resolution A).

    The LLM may only *raise* a rule-defined risk: a matched code with
    ``is_reservation_mutation`` true forces ``outcome="flag"`` regardless of
    what the LLM proposed. Unknown/None code ⇒ uncategorized, issue_code=None,
    outcome preserved.

    ``history`` is extraction-only context (D30): it is forwarded *solely* to
    ``llm.classify`` and never participates in the deterministic risk pass.
    With ``history=""`` (default) the call is byte-identical to the prior
    two-argument call (back-compat). ``requested_checkout`` (D24) is parsed
    conservatively: empty/None/unparseable ISO ⇒ ``None``, never raises.
    """
    # Extraction-only: history forwarded ONLY to the LLM; default keeps the
    # legacy two-arg call byte-identical for back-compat.
    if history:
        raw = await llm.classify(text, catalog, history)  # may raise LLMUnavailable
    else:
        raw = await llm.classify(text, catalog)           # may raise LLMUnavailable
    by_code = {c["code"]: c for c in catalog}
    result = []
    for item in raw:
        code = item.get("issue_code")
        cc = by_code.get(code) if code else None
        outcome = item["outcome"]
        if cc and cc.get("is_reservation_mutation"):    # Resolution A
            outcome = "flag"                            # raise only
        rc_raw = item.get("requested_checkout")
        rc = None
        if rc_raw:
            try:
                rc = dt.datetime.fromisoformat(rc_raw)
            except (ValueError, TypeError):
                rc = None                               # conservative
        result.append(TriagedChild(
            text=item["text"],
            issue_code=code if cc else None,
            outcome=TriageOutcome(outcome),
            uncategorized=cc is None,
            is_problem_report=bool(item.get("is_problem_report")),
            requested_checkout=rc,
        ))
    return result


def triage(child_text: str) -> TriagedChild:
    """Slot-completeness + deterministic risk rulebook → outcome (D5/D30).

    Reservation/revenue mutations always FLAG, never AUTO (D24).
    Priority tier is derived from the issue code's SLA preset and is
    independent of this outcome (D20) — never from guest-asserted urgency.
    """
    raise NotImplementedError
