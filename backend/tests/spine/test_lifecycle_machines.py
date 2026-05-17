"""Per-entity lifecycle machines (C3) — pure legal-transition matrices.

Each machine exposes ``legal(frm, to) -> bool`` over the exact state
vocabulary of its model CHECK constraint (ck_child_state / ck_wo_state /
ck_esc_state / ck_glitch_state). No DB, no I/O. Also asserts the package
conversion preserves the back-compat ``ChildState`` re-export.
"""
from conduit.shared.domain.lifecycle import (child as child_machine,
                                             escalation as escalation_machine,
                                             glitch as glitch_machine,
                                             workorder as workorder_machine)


# --- child: the dispatch arc -------------------------------------------------

def test_child_dispatch_arc_legal():
    arc = [
        ("triaged", "routing"),
        ("routing", "pushed"),
        ("pushed", "accepted"),
        ("accepted", "in_progress"),
        ("in_progress", "done_pending_confirm"),
        ("done_pending_confirm", "closed"),
    ]
    for frm, to in arc:
        assert child_machine.legal(frm, to) is True, f"{frm}->{to}"


def test_child_reopen_from_done_pending_confirm():
    assert child_machine.legal("done_pending_confirm", "reopened") is True


def test_child_broadcast_fanout_legal():
    assert child_machine.legal("routing", "broadcast") is True
    assert child_machine.legal("broadcast", "accepted") is True


def test_child_dispatch_leg_carry_to_done_pending_confirm_legal():
    """§7.2 spec-faithful machine semantics (NOT a weakening).

    The dispatch child HOLDS at ``routing`` while the WorkOrder carries the
    visible leg (pushed→accepted→in_progress→completed); no production code
    advances the child past ``routing``. Spec §7.2: "WorkOrder → completed ⇒
    child → done_pending_confirm" — NOT conditional on the child being
    in_progress. So the C4 WO→completed carry must legally resume the child's
    own arc at ``done_pending_confirm`` from whichever dispatch-leg state it
    holds. These edges are now LEGAL by design (additively added — every
    pre-existing edge is retained; the genuinely-illegal jumps below, e.g.
    ``intake``/``triaged`` → done_pending_confirm and ``closed``-origin jumps,
    stay illegal)."""
    assert child_machine.legal("routing", "done_pending_confirm") is True
    assert child_machine.legal("pushed", "done_pending_confirm") is True
    assert child_machine.legal("broadcast", "done_pending_confirm") is True
    assert child_machine.legal("accepted", "done_pending_confirm") is True
    assert child_machine.legal("in_progress", "done_pending_confirm") is True
    # NOT a blanket relaxation — non-dispatch-leg / terminal origins stay
    # illegal jumps to done_pending_confirm.
    assert child_machine.legal("intake", "done_pending_confirm") is False
    assert child_machine.legal("triaged", "done_pending_confirm") is False
    assert child_machine.legal("closed", "done_pending_confirm") is False


def test_child_any_active_state_can_cancel():
    for active in ("triaged", "routing", "pushed", "broadcast", "accepted",
                   "in_progress", "done_pending_confirm"):
        assert child_machine.legal(active, "cancelled") is True, active


def test_child_illegal_jumps():
    assert child_machine.legal("triaged", "closed") is False
    assert child_machine.legal("closed", "in_progress") is False
    assert child_machine.legal("intake", "done_pending_confirm") is False
    assert child_machine.legal("accepted", "triaged") is False
    assert child_machine.legal("closed", "cancelled") is False
    assert child_machine.legal("done_pending_confirm", "in_progress") is False


def test_child_preserves_old_legal_map():
    # The merged module's _LEGAL — these MUST stay legal (additive union).
    assert child_machine.legal("intake", "triaged") is True
    assert child_machine.legal("triaged", "answered") is True
    assert child_machine.legal("triaged", "concierge_queue") is True
    assert child_machine.legal("answered", "closed") is True
    assert child_machine.legal("answered", "reopened") is True
    assert child_machine.legal("reopened", "concierge_queue") is True


# --- workorder ---------------------------------------------------------------

def test_workorder_arc_legal():
    assert workorder_machine.legal("created", "pushed") is True
    assert workorder_machine.legal("created", "broadcast") is True
    assert workorder_machine.legal("pushed", "accepted") is True
    assert workorder_machine.legal("broadcast", "accepted") is True
    assert workorder_machine.legal("accepted", "in_progress") is True
    assert workorder_machine.legal("in_progress", "completed") is True


def test_workorder_cancel_legal():
    for active in ("created", "pushed", "broadcast", "accepted",
                   "in_progress"):
        assert workorder_machine.legal(active, "cancelled") is True, active


def test_workorder_illegal_jumps():
    assert workorder_machine.legal("created", "completed") is False
    assert workorder_machine.legal("completed", "in_progress") is False
    assert workorder_machine.legal("created", "in_progress") is False
    assert workorder_machine.legal("accepted", "created") is False
    assert workorder_machine.legal("completed", "cancelled") is False


# --- escalation --------------------------------------------------------------

def test_escalation_open_resolutions_legal():
    for to in ("approved", "edited", "overridden", "auto_proceeded",
               "hard_escalated"):
        assert escalation_machine.legal("open", to) is True, to


def test_escalation_illegal_jumps():
    assert escalation_machine.legal("approved", "open") is False
    assert escalation_machine.legal("open", "open") is False
    assert escalation_machine.legal("edited", "overridden") is False
    assert escalation_machine.legal("approved", "hard_escalated") is False


# --- glitch ------------------------------------------------------------------

def test_glitch_open_resolutions_legal():
    for to in ("held_open", "auto_closed", "closed"):
        assert glitch_machine.legal("open", to) is True, to


def test_glitch_held_open_can_close():
    assert glitch_machine.legal("held_open", "closed") is True


def test_glitch_illegal_jumps():
    assert glitch_machine.legal("closed", "open") is False
    assert glitch_machine.legal("auto_closed", "closed") is False
    assert glitch_machine.legal("open", "open") is False
    assert glitch_machine.legal("closed", "held_open") is False


# --- back-compat re-export ---------------------------------------------------

def test_childstate_reexport_still_works():
    from conduit.shared.domain.lifecycle import ChildState
    assert ChildState.INTAKE.value == "intake"
    assert ChildState.TRIAGED.value == "triaged"
    assert ChildState.ROUTING.value == "routing"
    assert ChildState.PUSHED.value == "pushed"
    assert ChildState.BROADCAST.value == "broadcast"
    assert ChildState.ACCEPTED.value == "accepted"
    assert ChildState.IN_PROGRESS.value == "in_progress"
    assert ChildState.DONE_PENDING_CONFIRM.value == "done_pending_confirm"
    assert ChildState.ANSWERED.value == "answered"
    assert ChildState.CONCIERGE_QUEUE.value == "concierge_queue"
    assert ChildState.CLOSED.value == "closed"
    assert ChildState.REOPENED.value == "reopened"
    assert ChildState.CANCELLED.value == "cancelled"
    assert ChildState.CLARIFYING.value == "clarifying"
    # Same object as the moved definition in lifecycle.child.
    assert ChildState is child_machine.ChildState


def test_legacy_transition_still_importable():
    # The merged consumers do ``from conduit.shared.domain import lifecycle``
    # then call ``lifecycle.transition`` — that name must still resolve.
    from conduit.shared.domain import lifecycle
    assert callable(lifecycle.transition)


# --- C4: lifecycle.transition orchestrator (DB-backed) -----------------------

import datetime as dt  # noqa: E402
import uuid  # noqa: E402

import pytest  # noqa: E402
import sqlalchemy as sa  # noqa: E402

from conduit.core.exceptions import ConflictError  # noqa: E402
from conduit.shared.domain import lifecycle  # noqa: E402
from conduit.shared.models import (CrossDeptNotification, Event,  # noqa: E402
                                   EventChildTriaged,
                                   EventChildDonePendingConfirm,
                                   EventWorkOrderCompleted, Timer, WorkOrder)


async def _wo_on(db, child, *, state: str, kind: str = "dispatch",
                 routing_model: str = "section_pooled",
                 priority_tier: str = "P3") -> WorkOrder:
    """Build a WorkOrder on ``child`` already advanced to ``state`` (the WO
    machine is created->pushed->accepted->in_progress->completed, so the row
    is constructed at the desired pre-transition state directly)."""
    wo = WorkOrder(child_id=child.id, kind=kind, routing_model=routing_model,
                   priority_tier=priority_tier, state=state)
    db.add(wo)
    await db.flush()
    return wo


async def test_workorder_completed_orchestrates_child_and_xdn(db, make_child):
    child = await make_child(db)
    # Child must be on the dispatch arc so it can move to done_pending_confirm.
    child.state = "in_progress"
    db.add(child)
    await db.flush()
    wo = await _wo_on(db, child, state="in_progress")

    await lifecycle.transition(db, wo, "completed", actor=None,
                               target_department="engineering",
                               xdn_reason="follow-up needed")
    await db.flush()

    # (a) state changed
    assert wo.state == "completed"
    # (b) exactly ONE work_order_completed event + its detail
    ev = (await db.execute(sa.select(Event)
          .where(Event.type == "work_order_completed"))).scalars().all()
    assert len(ev) == 1
    det = (await db.execute(
        sa.select(EventWorkOrderCompleted))).scalars().all()
    assert len(det) == 1 and det[0].work_order_id == wo.id
    # (c) cross-entity hop: linked child -> done_pending_confirm + its event
    await db.refresh(child)
    assert child.state == "done_pending_confirm"
    cev = (await db.execute(sa.select(Event)
           .where(Event.type == "child_done_pending_confirm"))
           ).scalars().all()
    assert len(cev) == 1
    cdet = (await db.execute(
        sa.select(EventChildDonePendingConfirm))).scalars().all()
    assert len(cdet) == 1 and cdet[0].child_id == child.id
    # (c cont.) downstream dept declared via ctx ⇒ a CrossDeptNotification row
    xdn = (await db.execute(
        sa.select(CrossDeptNotification))).scalars().all()
    assert len(xdn) == 1
    assert xdn[0].source_work_order_id == wo.id
    assert xdn[0].target_department == "engineering"
    assert xdn[0].child_id == child.id


async def test_workorder_completed_carries_routing_held_child(db, make_child):
    """§7.2 real path: the dispatch child HOLDS at ``routing`` while the
    WorkOrder carries the visible leg (E1 design — no production code advances
    the child past ``routing``). On WorkOrder → completed the C4 hop MUST
    carry the routing-held child → ``done_pending_confirm`` and emit EXACTLY
    ONE ``child_done_pending_confirm`` event via the C4 single writer. This is
    the journey the real portal APIs drive (no test-side model write of a
    journey transition)."""
    child = await make_child(db)
    child.state = "routing"          # the REAL holding state (intake/routing)
    db.add(child)
    await db.flush()
    wo = await _wo_on(db, child, state="in_progress")

    await lifecycle.transition(db, wo, "completed", actor=None)
    await db.flush()

    await db.refresh(child)
    assert child.state == "done_pending_confirm"
    cev = (await db.execute(sa.select(Event)
           .where(Event.type == "child_done_pending_confirm"))
           ).scalars().all()
    assert len(cev) == 1
    cdet = (await db.execute(
        sa.select(EventChildDonePendingConfirm))).scalars().all()
    assert len(cdet) == 1 and cdet[0].child_id == child.id


async def test_workorder_illegal_transition_is_side_effect_free(db,
                                                                make_child):
    child = await make_child(db)
    wo = await _wo_on(db, child, state="created")  # created->completed illegal

    before_ev = (await db.execute(
        sa.select(sa.func.count()).select_from(Event))).scalar_one()

    with pytest.raises(ConflictError):
        await lifecycle.transition(db, wo, "completed", actor=None)
    await db.flush()

    # No state change, no event written — illegal == zero side effects.
    await db.refresh(wo)
    assert wo.state == "created"
    after_ev = (await db.execute(
        sa.select(sa.func.count()).select_from(Event))).scalar_one()
    assert after_ev == before_ev
    assert (await db.execute(sa.select(sa.func.count())
            .select_from(EventWorkOrderCompleted))).scalar_one() == 0


async def test_child_transition_back_compat_single_event(db, make_child):
    # Mirrors test_lifecycle.py::test_transition_sets_state_and_appends_event:
    # the legacy child path emits exactly ONE child_* event, unchanged.
    child = await make_child(db)
    await lifecycle.transition(db, child, "triaged", actor_account_id=None)
    await db.flush()
    assert child.state == "triaged"
    ev = (await db.execute(sa.select(Event)
          .where(Event.type == "child_triaged"))).scalars().all()
    assert len(ev) == 1
    det = (await db.execute(sa.select(EventChildTriaged))).scalars().all()
    assert len(det) == 1 and det[0].child_id == child.id


async def test_child_routing_creates_work_order_and_arms_timers(db,
                                                                make_child):
    # D23: child -> routing creates a WorkOrder + arms accept_window and
    # fulfilment_sla timers in the same transaction.
    child = await make_child(db)
    child.state = "triaged"
    db.add(child)
    await db.flush()

    await lifecycle.transition(db, child, "routing", actor=None,
                               kind="dispatch",
                               routing_model="section_pooled",
                               priority_tier="P3")
    await db.flush()

    assert child.state == "routing"
    wo = (await db.execute(sa.select(WorkOrder)
          .where(WorkOrder.child_id == child.id))).scalars().all()
    assert len(wo) == 1
    timers = (await db.execute(sa.select(Timer)
              .where(Timer.child_id == child.id))).scalars().all()
    kinds = {t.type for t in timers}
    assert "accept_window" in kinds
    assert "fulfilment_sla" in kinds
    # exactly one child_routed event
    cev = (await db.execute(sa.select(Event)
           .where(Event.type == "child_routed"))).scalars().all()
    assert len(cev) == 1
