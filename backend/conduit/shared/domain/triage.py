"""Triage mechanism — cross-portal domain logic (not a portal slice).

Triggered from guest intake (conduit.guest.services.intake) but the mechanism
is shared and portal-agnostic. Mechanical, not vibe-based (D5/D30):
slot-completeness + a deterministic objective risk rulebook; the LLM may only
*raise* a rule-defined risk, never infer one from tone.

Pipeline (D35 → D5): decompose → per-child classify → per-child triage.
"""
from __future__ import annotations

import datetime as dt
import re
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
    issue_label: str | None = None  # D36 embed-derived label (split-echo)


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


# --- Deterministic D30 objective-risk lexicon (spec §7.2 / §7.4) -------------
# D30: the only risk triggers are the *objective* categories
# money / safety / move / mutation. Tone/urgency is NEVER a trigger (D20).
# Kept small, readable and word-boundary matched so a substring of an
# innocuous word cannot spuriously flag.
_RISK_SAFETY = (  # safety hazard → FLAG
    "flood", "flooding", "leak", "leaking", "fire", "smoke", "gas",
    "injur", "injured", "hurt", "bleeding", "electrical", "shock",
    "spark", "burn", "hazard", "broken glass", "carbon monoxide",
)
_RISK_MONEY = (  # money / billing dispute → FLAG
    "refund", "charge", "charged", "overcharge", "overcharged", "bill",
    "billed", "billing", "invoice", "payment", "dispute", "double charged",
)
_RISK_MOVE = (  # move / relocation request → FLAG (relocation-subflow §1)
    "relocate", "relocation", "move me", "move us", "move rooms",
    "change room", "change my room", "switch room", "switch rooms",
    "different room", "another room", "new room",
)
_RISK_MUTATION = (  # reservation / revenue mutation → FLAG, never AUTO (D24)
    "check out", "checkout", "check-out", "early checkout", "late checkout",
    "extend my stay", "extend stay", "stay longer", "cancel my reservation",
    "cancel reservation", "cancel my booking", "change my reservation",
    "modify my reservation", "extra night", "another night",
)

# D20: urgency / tone intensifiers carry NO risk meaning. Stripped before any
# decision so "URGENT!!! extra towels NOW" triages identically to
# "extra towels". (D30 invariant: tone never raises/lowers the outcome.)
_URGENCY_WORDS = (
    "urgent", "urgently", "asap", "now", "immediately", "right now",
    "please", "emergency", "quick", "quickly", "fast", "hurry",
)


def _strip_urgency(text: str) -> str:
    """Remove guest-asserted urgency/tone so the rulebook is tone-blind (D20).

    Drops intensifier words and punctuation emphasis ("!!!"). The result is
    used ONLY for the outcome decision; the original text is preserved on the
    returned ``TriagedChild.text``.
    """
    s = text.lower()
    s = s.replace("!", " ").replace("?", " ")
    for w in _URGENCY_WORDS:
        s = re.sub(rf"\b{re.escape(w)}\b", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def triage(child_text: str) -> TriagedChild:
    """Slot-completeness + deterministic risk rulebook → outcome (D5/D30).

    Pure: NO LLM, NO DB, NO clock. ``classify`` does extraction; ``triage``
    decides only the *outcome* from deterministic rules over the text.

    Rulebook (spec §7.2 / §7.4), evaluated in order:

    1. **FLAG** — an objective D30 risk category is present: safety hazard,
       money/billing dispute, a move/relocation request, or a
       reservation/revenue mutation. Reservation-mutation ⇒ FLAG, never AUTO
       (D24) — decided structurally from the text here since ``triage`` has
       no ``issue_code``.
    2. **CLARIFY** — too underspecified to act on: no actionable need/object
       once urgency/tone is stripped (e.g. "I need something", "help").
    3. **AUTO** — otherwise: a complete, low-risk, actionable request.

    Asserted urgency/tone never changes the outcome (D20/D30): intensifiers
    are stripped before deciding, so "URGENT!!! extra towels NOW" ≡
    "extra towels". Priority tier (derived elsewhere from the issue code's
    SLA preset) is independent of this outcome (D20).

    ``triage`` is text-only and assigns no code: ``issue_code=None`` /
    ``uncategorized=True`` matches the dataclass intent here (it decides the
    outcome, not the code) and leaves ``classify``'s construction unaffected.
    """
    probe = _strip_urgency(child_text)

    def _hit(lexicon: tuple[str, ...]) -> bool:
        return any(term in probe for term in lexicon)

    # (1) Objective D30 risk → FLAG (money / safety / move / mutation).
    if (_hit(_RISK_SAFETY) or _hit(_RISK_MONEY)
            or _hit(_RISK_MOVE) or _hit(_RISK_MUTATION)):
        outcome = TriageOutcome.FLAG
    # (2) Missing the core slot — no actionable need/object → CLARIFY.
    elif _is_underspecified(probe):
        outcome = TriageOutcome.CLARIFY
    # (3) Complete + low-risk + actionable → AUTO.
    else:
        outcome = TriageOutcome.AUTO

    return TriagedChild(
        text=child_text,
        issue_code=None,
        outcome=outcome,
        uncategorized=True,
    )


# D5 slot-completeness: a request is actionable only if it names *what* is
# wanted (an object/need), beyond a bare placeholder. Deterministic and
# small — phrases that are pure "I want help" with no object are CLARIFY.
_PLACEHOLDER_NEEDS = (
    "something", "anything", "stuff", "things", "thing",
)
_BARE_ASKS = (
    "help", "i need help", "need help", "i need something",
    "i need", "can you help", "assistance", "hello", "hi", "hey",
)


def _is_underspecified(probe: str) -> bool:
    """True when the (tone-stripped) text has no actionable object (D5).

    A request is underspecified if, after removing the asking frame, nothing
    concrete remains, or the only "object" is a placeholder ("something",
    "anything"). Pure string logic — no model, no I/O.
    """
    if not probe:
        return True
    if probe in _BARE_ASKS:
        return True
    # Strip a leading asking frame ("i need", "can i get", "please send"...).
    stripped = re.sub(
        r"^(can i (get|have)|could i (get|have)|i need|i want|i would like|"
        r"i'?d like|please (get|send|bring)|may i (get|have)|give me|"
        r"send me|bring me|get me)\b",
        "", probe,
    ).strip()
    # Drop filler so only the object (if any) is left.
    stripped = re.sub(
        r"\b(a|an|the|some|to|my|me|for|in|of|please)\b", " ", stripped)
    stripped = re.sub(r"\s+", " ", stripped).strip()
    if not stripped:
        return True
    # Only a placeholder noun and nothing else ⇒ still no real object.
    if stripped in _PLACEHOLDER_NEEDS:
        return True
    return False
