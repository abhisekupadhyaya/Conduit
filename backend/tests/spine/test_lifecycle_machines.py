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
