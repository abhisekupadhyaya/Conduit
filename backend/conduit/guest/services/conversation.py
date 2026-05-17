"""Guest dispatch conversation — confirm / reopen / cancel (Spec §8, §9.2).

Orchestration only. The guarded guest actions on a dispatch child: the guest
has the final word on closure (D8), may reopen if not actually resolved, and
may cancel any time UNTIL Closed (D6/D37). Ownership + state guards raise the
merged ``core/exceptions`` (foreign child → ``NotFoundError`` → 404; illegal
state, e.g. cancel after closed → ``ConflictError`` → 409); the state change +
its single append-only event go through the C4 ``lifecycle.transition`` writer
path ONLY (no parallel writer, no reimplemented effecting). The DAL is
add-only / no-flush / no-commit; this service flushes; the API commits at the
edge. Reads never commit.
"""
from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from conduit.core.exceptions import ConflictError, NotFoundError
from conduit.guest.dal import requests as rdal
from conduit.shared.domain import lifecycle


async def _owned_child(s: AsyncSession, actor, child_id: uuid.UUID):
    """Resolve the child ONLY within the caller's scope (no cross-stay leak).

    A non-existent OR foreign child is INDISTINGUISHABLE from the caller's
    point of view → ``NotFoundError`` (404) in BOTH cases (no enumeration
    oracle)."""
    child = await rdal.get_dispatch_child_for_guest(s, child_id, actor.id)
    if child is None:
        raise NotFoundError("request not found")
    return child


async def confirm(s: AsyncSession, actor, child_id: uuid.UUID) -> dict:
    """Guest confirms the dispatched work is done → child Closed (D8).

    Foreign child → 404; not awaiting confirmation
    (state != ``done_pending_confirm``) → 409."""
    child = await _owned_child(s, actor, child_id)
    if child.state != "done_pending_confirm":
        raise ConflictError("request is not awaiting confirmation")
    await lifecycle.transition(s, child, "closed",
                               actor_account_id=actor.id)
    return {"child_id": str(child.id), "state": child.state}


async def reopen(s: AsyncSession, actor, child_id: uuid.UUID) -> dict:
    """Guest says it is NOT actually resolved → child Reopened.

    Foreign child → 404; not awaiting confirmation → 409."""
    child = await _owned_child(s, actor, child_id)
    if child.state != "done_pending_confirm":
        raise ConflictError("request is not awaiting confirmation")
    await lifecycle.transition(s, child, "reopened",
                               actor_account_id=actor.id)
    return {"child_id": str(child.id), "state": child.state}


async def cancel(s: AsyncSession, actor, child_id: uuid.UUID) -> dict:
    """Guest cancels — allowed UNTIL Closed (D6). Already closed → 409.

    The committed servicer IS notified: the C4 ``child_cancelled``
    append-only event the orchestrator emits on the ``->cancelled`` hop IS
    the notification record (D37) — reused, not a parallel notify path.
    ``lifecycle.transition`` itself raises ``ConflictError`` for an illegal
    ``state->cancelled`` (closed/answered/reopened/cancelled have no
    ``->cancelled`` edge), which the API maps to 409; an explicit guard makes
    the 'already closed' contract loud."""
    child = await _owned_child(s, actor, child_id)
    if child.state in ("closed", "cancelled"):
        raise ConflictError("request is already closed")
    await lifecycle.transition(s, child, "cancelled",
                               actor_account_id=actor.id)
    return {"child_id": str(child.id), "state": child.state}
