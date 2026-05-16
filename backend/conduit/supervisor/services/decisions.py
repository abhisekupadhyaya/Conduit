# conduit/supervisor/services/decisions.py
"""Supervisor decision actions — the decision queue + the single
``/resolve`` (Spec §8 / §7.4 / §9.2).

Orchestration ONLY. ``resolve`` maps the supervisor's
``{approve|edit|override}`` to the §7.4 outcome vocabulary
``{approved|edited|overridden}`` and calls the SINGLE executor
``spine.apply_recommendation`` — passing the supervisor as ``actor`` and,
for edit/override, the supervisor-supplied action + payload. It does NOT
reimplement resolution logic and adds NO parallel writer: silence ≡
approve stays STRUCTURAL because the timer auto-proceed path
(engine/runner, D2/D3) calls the EXACT same ``apply_recommendation`` —
the only post-state difference is ``resolved_by_account_id`` (None for
auto-proceed).

Guards raise the merged ``core/exceptions``: an absent / already-resolved
escalation → ``ConflictError`` (409, no enumeration oracle); a malformed
edit/override (missing required action) → ``ValidationError`` (422). The
DAL is add-only / no-flush / no-commit; this service flushes; the API
commits at the edge. Reads never commit.
"""
from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from conduit.core.deps import Actor
from conduit.core.exceptions import ConflictError, ValidationError
from conduit.shared.engine import spine
from conduit.supervisor.dal import decisions as ddal

# The supervisor action → §7.4 outcome the single executor consumes.
# ``approve`` runs the STORED recommendation verbatim; ``edit``/``override``
# carry a supervisor-supplied typed action + payload.
_ACTION_TO_OUTCOME = {
    "approve": "approved",
    "edit": "edited",
    "override": "overridden",
}
# Outcomes that require a supervisor-supplied typed action in ``payload``.
_SUPPLIED_OUTCOMES = ("edited", "overridden")


async def list_decisions(s: AsyncSession, *, status: str | None = None
                         ) -> list[dict]:
    """The decision queue (open by default). A read — never commits."""
    return await ddal.list_decisions(s, status=status)


async def resolve(s: AsyncSession, actor: Actor, escalation_id: uuid.UUID,
                  *, action: str, payload: dict | None) -> dict:
    """THE single human resolve path (Spec §7.4). Maps action→outcome and
    calls ``spine.apply_recommendation`` (the ONLY executor) with the
    supervisor as ``actor``.

    Unknown action → 422 (defensive — the schema enum already constrains).
    No open escalation (absent or already resolved) → 409. A malformed
    edit/override (no typed action supplied) → 422 (surfaced as a clean
    ValidationError rather than the spine's internal ConflictError).
    """
    outcome = _ACTION_TO_OUTCOME.get(action)
    if outcome is None:
        raise ValidationError(f"unknown decision action {action!r}")

    esc = await ddal.get_open_escalation(s, escalation_id)
    if esc is None:
        # Absent OR already-resolved — indistinguishable (no oracle).
        raise ConflictError("escalation is not open / already resolved")

    supplied_action = None
    supplied_payload = None
    if outcome in _SUPPLIED_OUTCOMES:
        # edit/override MUST carry the supervisor-supplied typed action;
        # validate HERE so a bad payload is a clean 422 (not the spine's
        # internal "outcome requires a supervisor-supplied action" 409).
        body = dict(payload or {})
        supplied_action = body.pop("action", None)
        if not supplied_action:
            raise ValidationError(
                f"{action!r} requires payload.action (the typed "
                "recommendation action to apply)")
        supplied_payload = body

    # The SINGLE executor — NOT reimplemented. The API just mapped
    # action→outcome and passes the supervisor as actor; the spine effects
    # the typed action, transitions the escalation, sets the resolver +
    # resolved_at, increments cycle_count, and enforces the D21 bound.
    await spine.apply_recommendation(
        s, esc, outcome=outcome, action=supplied_action,
        payload=supplied_payload, actor=actor.id)
    await s.flush()
    return {
        "escalation_id": str(esc.id),
        "state": esc.state,
        "resolved_by_account_id": (
            str(esc.resolved_by_account_id)
            if esc.resolved_by_account_id is not None else None),
    }
