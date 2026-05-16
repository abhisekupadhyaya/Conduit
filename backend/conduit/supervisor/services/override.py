# conduit/supervisor/services/override.py
"""Supervisor override actions — the D6 god-mode (Spec §8 "Supervisor
children/override").

D6 god-mode is NOT a special bypass node and NOT a parallel writer. It is
exactly: the supervisor can ACT from ANY *active* state. The effecting
machinery is the SAME as everywhere else in the spine:

* ``cancel`` → the C4 ``lifecycle.transition`` single writer path
  (``child -> cancelled``). The child machine (C4) makes
  ``<any active state> -> cancelled`` a LEGAL guarded edge (D6 — the
  supervisor interrupt is a guarded transition, not a node). An ILLEGAL
  terminal transition (e.g. cancel an already-``cancelled``/``closed``
  child) still raises ``ConflictError`` → 409: god-mode lets the
  supervisor act from any *active* state, it does NOT let it violate the
  state machine.
* ``takeover`` / ``reassign`` → the established D2/D6 in-place WorkOrder
  assignee mutation pattern (identical to ``spine._execute_action``'s
  reassign hop): swap ``assigned_servicer_id`` in place; the accountable
  owner is UNCHANGED (D12 — the owner stays accountable to Closed/SLA
  regardless of who later services). An assignee swap is NOT a child/WO
  state change, so no ``transition`` event is emitted (mirrors the spine).

Target semantics (spec-faithful; the spec leaves the takeover target
implicit — see the inline note):

* ``reassign`` — REQUIRES an explicit ``target_servicer_id`` (hand the
  work to a named servicer).
* ``takeover`` — the acting supervisor/duty-manager BECOMES the assignee
  by default (the literal "I am taking this over"); an OPTIONAL
  ``target_servicer_id`` lets the supervisor instead hand it to a named
  servicer (a supervisor-directed takeover). Minimal spec-faithful choice.

Guards raise the merged ``core/exceptions``: an unknown child →
``NotFoundError`` (404); an illegal terminal transition or a child with
no WorkOrder to act on → ``ConflictError`` (409). The DAL is add-only /
no-flush / no-commit; the C4 ``transition`` flushes for the event id; this
service adds no extra flush; the API commits at the edge. Reads never
commit.
"""
from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from conduit.core.deps import Actor
from conduit.core.exceptions import ConflictError, NotFoundError
from conduit.shared.domain import lifecycle
from conduit.supervisor.dal import children as cdal


async def list_children(s: AsyncSession, *,
                        child_id: uuid.UUID | None = None,
                        state: str | None = None) -> list[dict]:
    """The global task explorer (Spec §8). A read — never commits;
    delegates to the self-contained supervisor DAL (Resolution E)."""
    return await cdal.list_children(s, child_id=child_id, state=state)


async def _require_child(s: AsyncSession, child_id: uuid.UUID):
    c = await cdal.get_child(s, child_id)
    if c is None:
        raise NotFoundError(f"child {child_id} not found")
    return c


async def _require_work_order(s: AsyncSession, child_id: uuid.UUID):
    wo = await cdal.child_work_order(s, child_id)
    if wo is None:
        # Nothing to take over / reassign — the child has no dispatch
        # WorkOrder (e.g. a no-dispatch / answered child). A conflict, not
        # a 404 (the child exists; the action is just not applicable).
        raise ConflictError(
            f"child {child_id} has no WorkOrder to override")
    return wo


async def takeover(s: AsyncSession, actor: Actor, child_id: uuid.UUID,
                   *, target_servicer_id: str | None = None) -> dict:
    """D6 takeover — works from ANY active state. In-place assignee swap on
    the child's WorkOrder (the D2/D6 entity-mutation pattern). The acting
    supervisor BECOMES the assignee by default; an explicit
    ``target_servicer_id`` hands it to a named servicer instead. The
    accountable owner is UNCHANGED (D12)."""
    await _require_child(s, child_id)
    wo = await _require_work_order(s, child_id)
    new_assignee = target_servicer_id if target_servicer_id else actor.id
    wo.assigned_servicer_id = new_assignee
    s.add(wo)
    return {"child_id": str(child_id), "child_state": None,
            "assigned_servicer_id": str(new_assignee),
            "accountable_owner_id": (
                str(wo.accountable_owner_id)
                if wo.accountable_owner_id is not None else None)}


async def reassign(s: AsyncSession, actor: Actor, child_id: uuid.UUID,
                   *, target_servicer_id: str) -> dict:
    """D6 reassign — works from ANY active state. In-place assignee swap on
    the child's WorkOrder to the explicit ``target_servicer_id`` (the
    D2/D6 entity-mutation pattern). The accountable owner is UNCHANGED
    (D12)."""
    await _require_child(s, child_id)
    wo = await _require_work_order(s, child_id)
    wo.assigned_servicer_id = target_servicer_id
    s.add(wo)
    return {"child_id": str(child_id), "child_state": None,
            "assigned_servicer_id": str(target_servicer_id),
            "accountable_owner_id": (
                str(wo.accountable_owner_id)
                if wo.accountable_owner_id is not None else None)}


async def cancel(s: AsyncSession, actor: Actor,
                 child_id: uuid.UUID) -> dict:
    """D6 cancel — the supervisor interrupt. Transitions the child to
    ``cancelled`` via the C4 ``lifecycle.transition`` SINGLE writer (one
    ``child_cancelled`` event). Legal from ANY active state (the child
    machine makes ``<active> -> cancelled`` a guarded edge — D6); an
    already-terminal child raises ``ConflictError`` → 409 (god-mode does
    NOT bypass the machine's legality)."""
    child = await _require_child(s, child_id)
    # The SINGLE writer path. An illegal terminal transition raises
    # ConflictError BEFORE any side effect (the C4 guard-first contract) —
    # NOT a special bypass: the same guarded machinery as everywhere.
    await lifecycle.transition(s, child, "cancelled",
                               actor_account_id=actor.id)
    return {"child_id": str(child_id), "child_state": child.state,
            "assigned_servicer_id": None, "accountable_owner_id": None}
