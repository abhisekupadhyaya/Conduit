"""Recommendation mechanism — deterministic action + templated rationale.

Pure (Spec §7.4): no DB, no I/O, no clock. ``context`` is an explicit
already-fetched inputs object (routing Selection result for ``stall``,
available-room lookup for ``servicer_raised``, flag verdict for
``triage_flag``). Effecting (persisting the Recommendation row, executing
the action) lives in the Phase C4 lifecycle orchestrator, never here.

The LLM is boxed (D5/D30): the ACTION and PARAMS are chosen by deterministic
Python rules — never by the LLM — so auto-proceed (D5/D30) can execute the
typed action safely and never runs free-form text. ``llm`` is an injectable
callable seam that only RENDERS the rationale string; the default
``_stub_llm`` returns the deterministic template verbatim (no network, no
free-form). The trigger/action string vocabularies match the model CHECK
constraints exactly (``ck_esc_trigger`` / ``ck_rec_action``).
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

# Mirrors Escalation.ck_esc_trigger exactly.
_TRIGGERS = ("triage_flag", "stall", "servicer_raised")
# Mirrors Recommendation.ck_rec_action exactly.
_ACTIONS = (
    "reassign", "broadcast", "relocate", "extend_sla", "approve", "deny",
    "apply_reservation_mutation",
)


@dataclass(frozen=True)
class RecommendationDraft:
    """The pure recommendation decision. No side effects implied."""

    action: str
    params: dict[str, Any] = field(default_factory=dict)
    rationale_text: str = ""


def _stub_llm(template: str) -> str:
    """The boxed default seam (D5/D30): return the templated rationale
    verbatim — no network, no free-form inference."""
    return template


def build(
    *,
    trigger: str,
    child: Any,
    context: Any,
    llm: Callable[[str], str] = _stub_llm,
) -> RecommendationDraft:
    """Deterministic recommendation per Spec §7.4.

    The action/params branch is pure Python keyed off ``trigger`` + the
    already-fetched ``context``; the ``llm`` seam only renders the rationale
    string from a deterministic template (stubbed by default).
    """
    if trigger not in _TRIGGERS:
        raise ValueError(f"unknown trigger: {trigger!r}")

    if trigger == "stall":
        # §7.4: stall → routing.select excluding the stalled assignee. A
        # single reassign target → reassign; else → broadcast.
        target = context.get("reassign_target")
        if target is not None:
            action = "reassign"
            params: dict[str, Any] = {"target_account_id": target}
            template = (
                f"Assignee stalled; reassigning to {target} via the same "
                f"routing rule with the stalled assignee excluded."
            )
        else:
            action = "broadcast"
            params = {"broadcast_pool": context.get("broadcast_pool", [])}
            template = (
                "Assignee stalled with no single reassign target; "
                "broadcasting to the eligible pool."
            )
    elif trigger == "servicer_raised":
        # §7.4: servicer-raised "can't fix" → relocate to a deterministic
        # available room if one was found, else extend the SLA.
        room = context.get("available_room_id")
        if room is not None:
            action = "relocate"
            params = {"target_room_id": room}
            template = (
                f"Servicer cannot fix in place; relocating guest to the "
                f"available room {room}."
            )
        else:
            action = "extend_sla"
            params = {"extend_seconds": context.get("extend_seconds")}
            template = (
                "Servicer cannot fix and no room is available; "
                "extending the SLA window."
            )
    else:  # triage_flag
        # §7.4: triage-flag → approve / deny from the flag verdict. Ambiguity
        # note: §7.4 names approve|deny but not the exact verdict token; we
        # take the minimal spec-faithful rule — verdict == "approve" →
        # approve, anything else → deny (conservative default).
        rc = context.get("requested_checkout")
        if rc is not None:
            # D24 answer↔action: a reservation-mutation flag carries the
            # already-extracted target (persisted at intake — the LLM is
            # NEVER in the auto-proceed path; D5/D30).
            action = "apply_reservation_mutation"
            params = {"field": "check_out", "requested_value": rc}
            template = (
                f"Guest requested a checkout change to {rc}; applying the "
                f"reservation mutation on approval."
            )
        else:
            verdict = context.get("verdict")
            if verdict == "approve":
                action = "approve"
                template = (
                    "Triage flag reviewed; approving the flagged request."
                )
            else:
                action = "deny"
                template = (
                    "Triage flag reviewed; denying the flagged request."
                )
            params = {}

    return RecommendationDraft(
        action=action,
        params=params,
        rationale_text=llm(template),
    )
