"""Room selection mechanism — pure available-only eligibility.

Spec §7.1 / §4 decision ledger ("Eligible rooms"). Pure (no DB, no I/O,
no clock): the room/occupancy DB read belongs to the caller
(``spine._assemble_context``, engine-local session), never here. The
deterministic result is computed + persisted at recommendation-build on
``RecRelocate.target_room_id`` (D9/D30) — selection never re-runs in the
auto-proceed path.

Eligible = each room from the caller-ordered ``rooms`` with NO active
``Stay`` (available-only) whose id is neither occupied nor the guest's
current room. v1 has no ``Room`` type/rate logic (room-type model
deferred, D32/D24). Caller-supplied order is preserved verbatim
(deterministic, stable — no sorting/shuffling per §7.1). Empty ⇒
``(None, [])`` so ``recommendation.build`` falls back to the existing
``extend_sla`` (regression preserved).
"""
from __future__ import annotations

from collections.abc import Collection, Iterable


def select(
    *,
    rooms: Iterable[tuple[str, str]],
    occupied_room_ids: Collection[str],
    current_room_id: str,
) -> tuple[str | None, list[str]]:
    """Pick the deterministic available-only relocation target (§7.1).

    ``rooms`` is an ordered iterable of ``(room_id, room_label)`` tuples
    (caller controls order per §7.1). ``occupied_room_ids`` is the set of
    room_ids with an active ``Stay``. ``current_room_id`` is the guest's
    current room_id (always excluded, even if absent from ``rooms``).

    Returns ``(recommended_room_id | None, eligible_room_ids)`` where
    ``eligible`` keeps ``rooms`` order verbatim and ``recommended`` is the
    first eligible id (or ``None`` ⇒ caller falls back to ``extend_sla``).
    """
    occupied = set(occupied_room_ids)
    eligible = [
        room_id
        for room_id, _room_label in rooms
        if room_id not in occupied and room_id != current_room_id
    ]
    recommended = eligible[0] if eligible else None
    return recommended, eligible
