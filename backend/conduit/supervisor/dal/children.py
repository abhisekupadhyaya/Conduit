# conduit/supervisor/dal/children.py
"""Supervisor task-explorer reads (Spec §8 "Supervisor children/override" —
the D6 god-mode surface). Read-only: add-only / no-flush / no-commit (the
merged DAL discipline).

Resolution E (Spec §4 "Portal ownership"): the supervisor owns its OWN
task-explorer reads through THIS module; it must NOT import another
portal's DAL. The supervisor scope is GLOBAL by role (Spec §8 — the
supervisor sees everything; the read is NOT self-scoped, unlike the
servicer/guest portals which are account-scoped): it finds ANY
``ChildSubRequest`` in ANY state and joins, for each:

* its ``WorkOrder`` (the dispatch handle — assignee + accountable owner);
* its ``Escalation`` (the most recent — the decision-queue linkage);
* its ``Glitch`` (the recovery linkage).

Optional filters (``child_id`` / ``state``) narrow the global read; absent,
the full property-wide child set is returned. The read NEVER flushes or
commits.
"""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from conduit.shared.models import (Account, ChildSubRequest, Escalation,
                                   Glitch, IssueCode, WorkOrder)


async def get_child(s: AsyncSession,
                    child_id: uuid.UUID) -> ChildSubRequest | None:
    """The raw ``ChildSubRequest`` (ANY state) or ``None`` — the override
    service's lookup seam. Read-only."""
    return (await s.execute(
        select(ChildSubRequest).where(ChildSubRequest.id == child_id)
    )).scalar_one_or_none()


async def child_work_order(s: AsyncSession,
                           child_id: uuid.UUID) -> WorkOrder | None:
    """The child's ``WorkOrder`` (1:1 — ``work_order.child_id`` is unique)
    or ``None``. The override service mutates the assignee on this row in
    place (the D2/D6 entity-mutation pattern). Read-only."""
    return (await s.execute(
        select(WorkOrder).where(WorkOrder.child_id == child_id)
    )).scalar_one_or_none()


async def list_children(s: AsyncSession, *,
                        child_id: uuid.UUID | None = None,
                        state: str | None = None) -> list[dict]:
    """The global task explorer: ANY child in ANY state + its WorkOrder /
    Escalation / Glitch, optionally filtered by ``child_id`` and/or
    ``state``. Read-only — no flush, no commit.

    Supervisor scope is GLOBAL by role (Spec §8): no per-user narrowing —
    only the explicit ``?child_id`` / ``?state`` filters apply.
    """
    q = select(ChildSubRequest)
    if child_id is not None:
        q = q.where(ChildSubRequest.id == child_id)
    if state is not None:
        q = q.where(ChildSubRequest.state == state)
    children = (await s.execute(
        q.order_by(ChildSubRequest.created_at)
    )).scalars().all()

    out: list[dict] = []
    for c in children:
        wo = (await s.execute(select(WorkOrder).where(
            WorkOrder.child_id == c.id))).scalar_one_or_none()
        # Most-recent escalation for the child (an escalation resolves once;
        # there may be a chain across stall cycles — surface the latest).
        esc = (await s.execute(
            select(Escalation).where(Escalation.child_id == c.id)
            .order_by(Escalation.created_at.desc()).limit(1)
        )).scalar_one_or_none()
        gl = (await s.execute(select(Glitch).where(
            Glitch.child_id == c.id))).scalar_one_or_none()
        # Human-readable labels (the UI renders these, not raw ids).
        issue_label = None
        if c.issue_code_id is not None:
            issue_label = (await s.execute(select(IssueCode.label).where(
                IssueCode.id == c.issue_code_id))).scalar_one_or_none()
        servicer_name = None
        if wo is not None and wo.assigned_servicer_id is not None:
            servicer_name = (await s.execute(
                select(Account.display_name).where(
                    Account.id == wo.assigned_servicer_id)
            )).scalar_one_or_none()
        out.append({
            "child_id": str(c.id),
            "issue_label": issue_label,
            "state": c.state,
            "work_order": None if wo is None else {
                "assigned_servicer_id": (
                    str(wo.assigned_servicer_id)
                    if wo.assigned_servicer_id is not None else None),
                "servicer_name": servicer_name,
                "accountable_owner_id": (
                    str(wo.accountable_owner_id)
                    if wo.accountable_owner_id is not None else None),
                "state": wo.state,
            },
            "escalation": None if esc is None else {
                "escalation_id": str(esc.id),
                "trigger": esc.trigger,
                "state": esc.state,
            },
            "glitch": None if gl is None else {
                "glitch_id": str(gl.id),
                "state": gl.state,
            },
        })
    return out
