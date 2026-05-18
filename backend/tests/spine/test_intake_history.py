"""Task 13 — Intake conversation-window + persist requested_checkout +
reservation-mutation flag → spine seam (D24 answer↔action).

Seam proof: a prior grounded checkout answer + a "till 2pm" follow-up →
classify (history-aware) → a LATE_CHECKOUT issue code whose
``is_reservation_mutation`` forces ``outcome="flag"`` → the mutation rides
the spine's generic FLAG trigger into the decision queue with a
``Recommendation(action='apply_reservation_mutation')`` and the parsed
``requested_checkout`` persisted on the child.

Seeding reuses the EXACT FK-chain idiom proven in
tests/spine/test_supervisor_decisions.py::_seed_world /
tests/spine/test_intake_service.py (guest+active stay+section+issue code+
active SLAPreset+active EscalationLadder). The ``db``/``fake_llm`` fixtures
come from tests/spine/conftest.py.
"""
from __future__ import annotations

import datetime as dt
import uuid

import pytest
import sqlalchemy as sa

from conduit.guest.services import intake
from conduit.shared.models import (
    EscalationLadder,
    IssueCode,
    Property,
    Recommendation,
    Room,
    Section,
    SLAPreset,
    Stay,
)
from conduit.shared.models import Escalation


@pytest.mark.asyncio
async def test_followup_mutation_opens_escalation_with_requested_checkout(
        db, fake_llm, make_account):
    """A prior grounded checkout answer + a 'till 2pm' follow-up →
    classify (history-aware) → mutation code force-flag → escalation opened
    with a Recommendation(action='apply_reservation_mutation') and the
    parsed requested_checkout persisted on the child."""
    # --- Arrange the real FK chain (same shape as _seed_world /
    # seeded_guest_with_stay): guest Account + active Stay in
    # Room/Section/Property, an active P3 SLAPreset, a LATE_CHECKOUT issue
    # code with is_reservation_mutation=True, an active EscalationLadder
    # (the spine precondition; its duty manager is referenced by the ladder).
    guest = await make_account("guest", f"g-{uuid.uuid4().hex[:8]}")
    duty = await make_account("supervisor", f"dm-{uuid.uuid4().hex[:8]}")
    p = Property(name="T")
    db.add(p)
    await db.flush()
    sec = Section(property_id=p.id, label="S")
    db.add(sec)
    await db.flush()
    room = Room(section_id=sec.id, label="R")
    db.add(room)
    await db.flush()
    now = dt.datetime.now(dt.timezone.utc)
    stay = Stay(guest_account_id=guest.id, room_id=room.id, check_in=now,
                check_out=now + dt.timedelta(days=1), status="active")
    db.add(stay)
    await db.flush()
    sla = SLAPreset(property_id=p.id, tier="P3", accept_window_seconds=120,
                    fulfilment_sla_seconds=1800, supervisor_sla_seconds=900,
                    status="active")
    db.add(sla)
    await db.flush()
    ic = IssueCode(code="LATE_CHECKOUT", label="Late checkout",
                   department="front_desk", fulfilment_mode="no_dispatch",
                   routing_model="none", is_reservation_mutation=True,
                   sla_preset_id=sla.id, status="active")
    db.add(ic)
    await db.flush()
    db.add(EscalationLadder(property_id=p.id,
                            duty_manager_account_id=duty.id,
                            n_cycle_bound=3, status="active"))
    await db.flush()

    requested = "2026-05-16T14:00:00+00:00"

    # fake_llm.classify → ONE child mapped to the seeded LATE_CHECKOUT code
    # with the D24 extracted target. The seeded code's
    # is_reservation_mutation=True makes triage.classify force outcome=flag
    # (Resolution A) regardless of the proposed outcome.
    async def fclassify(t, cat, *a):
        return [{"text": t, "issue_code": "LATE_CHECKOUT",
                 "fulfilment_mode": "no_dispatch", "outcome": "no_dispatch",
                 "is_problem_report": False,
                 "requested_checkout": requested}]

    async def fground(q, ctx):
        return {"grounded": True, "leaves_no_dispatch": False,
                "answer": "Checkout is 11:00.", "used_kb_ids": [],
                "used_fields": []}

    fake_llm["classify"] = fclassify
    fake_llm["ground"] = fground

    # --- Act: the follow-up that should ride the spine.
    out = await intake.submit_request(db, guest, "can I get it till 2pm?")
    await db.flush()

    child_id = uuid.UUID(out["children"][0]["child_id"])

    # --- Assert: an Escalation(trigger='triage_flag') exists for the child.
    esc = (await db.execute(sa.select(Escalation).where(
        Escalation.child_id == child_id))).scalar_one()
    assert esc.trigger == "triage_flag"
    assert esc.state == "open"

    # --- Assert: a Recommendation(action='apply_reservation_mutation').
    rec = (await db.execute(sa.select(Recommendation).where(
        Recommendation.escalation_id == esc.id))).scalar_one()
    assert rec.action == "apply_reservation_mutation"

    # --- Assert: child.requested_checkout is the parsed datetime.
    from conduit.shared.models import ChildSubRequest
    child = (await db.execute(sa.select(ChildSubRequest).where(
        ChildSubRequest.id == child_id))).scalar_one()
    assert child.requested_checkout == dt.datetime(
        2026, 5, 16, 14, 0, tzinfo=dt.timezone.utc)
