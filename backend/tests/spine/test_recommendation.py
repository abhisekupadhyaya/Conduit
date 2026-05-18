"""Tests for the pure recommendation.build (Spec §7.4, D5/D30).

No DB, no I/O, no clock — every input is an explicit already-fetched
context object. The deterministic action/params are chosen by Python rules
per trigger; the LLM seam only renders the rationale string and is STUBBED
by default (LLM boxed — D5/D30), so auto-proceed never executes free-form
text.
"""
import datetime as dt
import uuid

from conduit.shared.domain.recommendation import (
    RecommendationDraft,
    _stub_llm,
    build,
)


# ---------------------------------------------------------------- stall ----
def test_stall_single_target_yields_reassign():
    target = uuid.uuid4()
    draft = build(
        trigger="stall",
        child={"id": uuid.uuid4()},
        context={"reassign_target": target, "stalled_id": uuid.uuid4()},
    )
    assert isinstance(draft, RecommendationDraft)
    assert draft.action == "reassign"
    assert draft.params == {"target_account_id": target}
    assert draft.rationale_text  # non-empty templated text
    assert isinstance(draft.rationale_text, str)


def test_stall_no_single_target_yields_broadcast():
    pool = [uuid.uuid4(), uuid.uuid4()]
    draft = build(
        trigger="stall",
        child={"id": uuid.uuid4()},
        context={"reassign_target": None, "broadcast_pool": pool},
    )
    assert draft.action == "broadcast"
    assert draft.params == {"broadcast_pool": pool}
    assert draft.rationale_text


# ------------------------------------------------------- servicer_raised ----
def test_servicer_raised_available_room_yields_relocate():
    room = uuid.uuid4()
    draft = build(
        trigger="servicer_raised",
        child={"id": uuid.uuid4()},
        context={"available_room_id": room, "extend_seconds": 3600},
    )
    assert draft.action == "relocate"
    assert draft.params == {"target_room_id": room}
    assert draft.rationale_text


def test_servicer_raised_no_room_yields_extend_sla():
    draft = build(
        trigger="servicer_raised",
        child={"id": uuid.uuid4()},
        context={"available_room_id": None, "extend_seconds": 7200},
    )
    assert draft.action == "extend_sla"
    assert draft.params == {"extend_seconds": 7200}
    assert draft.rationale_text


def test_servicer_raised_relocate_params_from_context_not_llm():
    # §7.2: the relocate target is the SELECTION result carried in
    # ``context['available_room_id']`` (pure-Python, deterministic) — the LLM
    # seam is boxed and may ONLY render the rationale string, never the
    # action/params. A garbage-returning seam must not move the picked room.
    picked = uuid.uuid4()
    sentinel = "FAKE-LLM-RATIONALE"

    def fake_llm(_template: str) -> str:
        return sentinel

    draft = build(
        trigger="servicer_raised",
        child={"id": uuid.uuid4()},
        context={"available_room_id": picked, "extend_seconds": 3600},
        llm=fake_llm,
    )
    assert draft.action == "relocate"               # deterministic
    assert draft.params == {"target_room_id": picked}  # from context
    assert draft.rationale_text == sentinel          # LLM only the rationale


# ----------------------------------------------------------- triage_flag ----
def test_triage_flag_verdict_approve():
    draft = build(
        trigger="triage_flag",
        child={"id": uuid.uuid4()},
        context={"verdict": "approve"},
    )
    assert draft.action == "approve"
    assert draft.params == {}
    assert draft.rationale_text


def test_triage_flag_verdict_deny():
    draft = build(
        trigger="triage_flag",
        child={"id": uuid.uuid4()},
        context={"verdict": "deny"},
    )
    assert draft.action == "deny"
    assert draft.params == {}
    assert draft.rationale_text


def test_triage_flag_reservation_mutation_yields_apply_action():
    when = dt.datetime(2026, 5, 16, 14, 0, tzinfo=dt.timezone.utc)
    draft = build(trigger="triage_flag", child={"id": 1},
                  context={"verdict": "approve", "requested_checkout": when})
    assert draft.action == "apply_reservation_mutation"
    assert draft.params == {"field": "check_out", "requested_value": when}
    assert draft.rationale_text


def test_triage_flag_without_mutation_still_approve_deny():
    d1 = build(trigger="triage_flag", child={"id": 1},
               context={"verdict": "approve"})
    d2 = build(trigger="triage_flag", child={"id": 1},
               context={"verdict": "nope"})
    assert d1.action == "approve" and d2.action == "deny"


# ---------------------------------------------------- llm seam + purity ----
def test_default_llm_is_the_boxed_stub():
    # The default seam must be the deterministic stub: no network, no
    # free-form. _stub_llm returns the templated rationale verbatim.
    template = "templated rationale for stall"
    assert _stub_llm(template) == template


def test_injected_llm_seam_only_renders_rationale_not_action():
    # An injected seam that returns garbage must NOT influence the
    # deterministic action/params — only the rationale string it returns.
    target = uuid.uuid4()
    sentinel = "FAKE-LLM-RENDERED-RATIONALE"

    def fake_llm(_template: str) -> str:
        return sentinel

    draft = build(
        trigger="stall",
        child={"id": uuid.uuid4()},
        context={"reassign_target": target},
        llm=fake_llm,
    )
    assert draft.action == "reassign"  # deterministic, not LLM-chosen
    assert draft.params == {"target_account_id": target}
    assert draft.rationale_text == sentinel


def test_determinism_byte_identical_output():
    cid = uuid.uuid4()
    target = uuid.uuid4()
    kwargs = dict(
        trigger="stall",
        child={"id": cid},
        context={"reassign_target": target},
    )
    a = build(**kwargs)
    b = build(**kwargs)
    assert a == b
    assert (a.action, a.params, a.rationale_text) == (
        b.action,
        b.params,
        b.rationale_text,
    )
