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

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from conduit.core.deps import Actor
from conduit.core.exceptions import ConflictError, ValidationError
from conduit.shared.domain import room_selection
from conduit.shared.engine import spine
from conduit.shared.models import (ChildSubRequest, Recommendation,
                                   RecRelocate, Room, Section, Stay)
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


async def _enrich_relocate_detail(s: AsyncSession, item: dict) -> None:
    """Spec §8 / §7.3 — enrich a ``relocate`` decision item's ``detail``
    (already a ``dict``) with the supervisor decision-card display data:
    ``current_room`` (the guest's room), ``recommended_room`` (the
    ALREADY-PERSISTED ``RecRelocate.target_room_id`` — auto-proceed safety:
    selection is NOT re-run to mutate the recommendation), and
    ``eligible_rooms`` (the pure C ``room_selection.select`` over the
    property's rooms+occupancy — the SAME inputs the spine used at build,
    via the spine's engine-local read helpers; selection rules are NOT
    re-implemented). DISPLAY-only: no persisted-recommendation mutation,
    no flush/commit. Non-relocate items are never passed here."""
    esc_id = uuid.UUID(item["escalation_id"])
    child = (await s.execute(
        sa.select(ChildSubRequest)
        .where(ChildSubRequest.id == uuid.UUID(item["child_id"]))
    )).scalar_one_or_none()
    if child is None:
        return

    # recommended_room := the PERSISTED target (display-only projection of
    # what approve/auto-proceed will apply — selection never re-runs here).
    rec_rel = (await s.execute(
        sa.select(RecRelocate).where(
            RecRelocate.recommendation_escalation_id == esc_id)
    )).scalar_one_or_none()

    current_room_id = await spine._current_room_for_child(s, child)
    property_id = await spine._property_id_for_child(s, child)
    # ``{id,label}`` shape (Spec §9.1/§10/§12 — the card shows room NUMBERS,
    # never raw ids; consistent with the de-UUID D17 direction). Labels come
    # from the SAME engine-local property-rooms read the spine used at build.
    label_by_id: dict[str, str] = {}
    elig_ids: list = []
    if property_id is not None:
        rooms, occupied = await spine._rooms_and_occupancy(s, property_id)
        label_by_id = {str(rid): label for rid, label in rooms}
        _recommended, elig_ids = room_selection.select(
            rooms=rooms, occupied_room_ids=occupied,
            current_room_id=current_room_id)

    async def _room_obj(rid) -> dict | None:
        if rid is None:
            return None
        key = str(rid)
        label = label_by_id.get(key)
        if label is None:                       # cross-property/edge fallback
            r = await s.get(Room, rid)
            label = r.label if r is not None else key
        return {"id": key, "label": label}

    rec = item["recommendation"]
    detail = rec.get("detail")
    if not isinstance(detail, dict):
        detail = {}
    detail["current_room"] = await _room_obj(current_room_id)
    detail["recommended_room"] = await _room_obj(
        rec_rel.target_room_id if rec_rel is not None else None)
    detail["eligible_rooms"] = [await _room_obj(rid) for rid in elig_ids]
    rec["detail"] = detail


async def list_decisions(s: AsyncSession, *, status: str | None = None
                         ) -> list[dict]:
    """The decision queue (open by default). A read — never commits.

    Spec §8 / §7.3: a ``relocate`` recommendation's ``detail`` is enriched
    (DISPLAY-only) with the decision-card data the supervisor acts on.
    Non-relocate items are returned unchanged. The ddal read is NOT
    re-implemented — this only post-processes its output."""
    items = await ddal.list_decisions(s, status=status)
    for item in items:
        rec = item.get("recommendation")
        if rec is not None and rec.get("action") == "relocate":
            await _enrich_relocate_detail(s, item)
    return items


async def _edited_relocate_action(s: AsyncSession, esc, body: dict
                                  ) -> tuple[str, dict] | None:
    """Spec §8 / §7.4 — the supervisor ``edit`` on a *relocate* escalation
    accepts ``payload={"new_room_id": "<uuid>"}``. Validate the room, then
    MAP it into the typed action the SINGLE executor already consumes for
    an edited relocate (``"relocate"`` + ``{"target_room_id": ...}`` — the
    existing ``spine._resolved_action`` edited path / the C4
    escalation→relocate hop; the executor is NOT re-implemented).

    Returns ``(action, payload)`` when this is an edited relocate, or
    ``None`` when the open escalation's recommendation is NOT a relocate
    (the caller falls back to the generic supplied-action path verbatim).

    UNKNOWN room id (no such Room / not in the escalation's property) →
    ``ValidationError`` (422). OCCUPIED room (an active Stay binds it) OR
    the guest's CURRENT room → ``ConflictError`` (409). A relocate edit
    that omits ``new_room_id`` falls through to the generic 422 guard.
    """
    rec = (await s.execute(
        sa.select(Recommendation)
        .where(Recommendation.escalation_id == esc.id)
    )).scalar_one_or_none()
    if rec is None or rec.action != "relocate":
        return None
    if "new_room_id" not in body:
        # Not the {new_room_id} variant — let the generic guard handle it
        # (a relocate edit MUST carry either new_room_id here or the
        # explicit typed action/payload the generic path validates).
        return None

    raw = body.get("new_room_id")
    try:
        new_room_id = uuid.UUID(str(raw))
    except (ValueError, TypeError, AttributeError):
        raise ValidationError(
            f"edit requires a valid new_room_id (got {raw!r})")

    child = (await s.execute(
        sa.select(ChildSubRequest)
        .where(ChildSubRequest.id == esc.child_id)
    )).scalar_one_or_none()
    if child is None:
        raise ValidationError("escalation has no child to relocate")
    property_id = await spine._property_id_for_child(s, child)

    # UNKNOWN: no such Room, or not in the escalation's property → 422.
    room_prop = (await s.execute(
        sa.select(Section.property_id)
        .select_from(Room)
        .join(Section, Section.id == Room.section_id)
        .where(Room.id == new_room_id)
    )).scalar_one_or_none()
    if room_prop is None or (property_id is not None
                             and room_prop != property_id):
        raise ValidationError(
            f"unknown room {new_room_id!r} (not a room in this property)")

    # CURRENT room → 409 (a no-op relocate; mirrors relocate_stay's
    # "already in that room" ConflictError, surfaced cleanly here).
    current_room_id = await spine._current_room_for_child(s, child)
    if current_room_id is not None and new_room_id == current_room_id:
        raise ConflictError("room is the guest's current room")

    # OCCUPIED: an ACTIVE Stay binds the target room → 409.
    occupied = (await s.execute(
        sa.select(Stay.id).where(Stay.room_id == new_room_id,
                                 Stay.status == "active").limit(1)
    )).scalar_one_or_none()
    if occupied is not None:
        raise ConflictError(f"room {new_room_id!r} is occupied")

    # Map into the typed action the single executor already consumes for an
    # edited relocate (the existing _resolved_action edited branch returns
    # ``(action, payload)`` and the C4 hop reads ``params['target_room_id']``).
    return "relocate", {"target_room_id": new_room_id}


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
        body = dict(payload or {})
        # Spec §8 — an ``edit`` on a *relocate* escalation accepts the
        # ``{new_room_id}`` variant: validate the room (unknown → 422;
        # occupied / current → 409) and MAP it into the typed relocate
        # action the SINGLE executor already consumes (NOT reimplemented).
        # Returns None when the open escalation is NOT a relocate → fall
        # through to the generic supplied-action path verbatim.
        mapped = None
        if action == "edit":
            mapped = await _edited_relocate_action(s, esc, body)
        if mapped is not None:
            supplied_action, supplied_payload = mapped
        else:
            # edit/override MUST carry the supervisor-supplied typed action;
            # validate HERE so a bad payload is a clean 422 (not the spine's
            # internal "outcome requires a supervisor-supplied action" 409).
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
