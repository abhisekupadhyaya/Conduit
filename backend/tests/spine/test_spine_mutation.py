import datetime as dt

from conduit.shared.engine import spine
from conduit.shared.models import RecApplyReservationMutation


def test_rec_detail_map_has_mutation():
    eid = __import__("uuid").uuid4()
    when = dt.datetime(2026, 5, 16, 14, 0, tzinfo=dt.timezone.utc)
    obj = spine._REC_DETAIL["apply_reservation_mutation"](
        eid, {"field": "check_out", "requested_value": when})
    assert isinstance(obj, RecApplyReservationMutation)
    assert obj.field == "check_out" and obj.requested_value == when


# ===========================================================================
# Task D24 — apply_reservation_mutation executor + emit_reservation_mutated
# ===========================================================================

import pytest


async def _seed_triage_mutation_scenario(db, make_account):
    """Full FK chain + a triaged reservation-mutation child with an open
    ``triage_flag`` Escalation carrying a stored
    ``apply_reservation_mutation`` Recommendation.

    Mirrors ``test_spine.py``'s ``_seed_stall_scenario`` scaffolding verbatim
    (same model constructors / flush discipline / EscalationLadder gating) —
    the only deltas are the spine-D24 specifics: the child is ``triaged``
    with ``requested_checkout`` set, the Escalation trigger is
    ``triage_flag``, and the Recommendation action is
    ``apply_reservation_mutation`` with its ``RecApplyReservationMutation``
    detail. No new factory/tick API is introduced.
    """
    import uuid

    import sqlalchemy as sa  # noqa: F401  (parity with _seed_stall_scenario)
    from conduit.shared.models import (ChildSubRequest, EscalationLadder,
                                       Escalation, IssueCode, Property,
                                       RecApplyReservationMutation,
                                       Recommendation, Request, Room,
                                       Section, SLAPreset, Stay)

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
    sla = SLAPreset(property_id=p.id, tier="P3",
                    accept_window_seconds=300,
                    fulfilment_sla_seconds=3600,
                    supervisor_sla_seconds=900,
                    status="active")
    db.add(sla)
    await db.flush()
    ic = IssueCode(code=f"IC-{uuid.uuid4().hex[:6]}", label="L",
                   department="front_desk", fulfilment_mode="no_dispatch",
                   routing_model="skill_matched", sla_preset_id=sla.id)
    db.add(ic)
    await db.flush()
    db.add(EscalationLadder(property_id=p.id,
                            duty_manager_account_id=duty.id,
                            n_cycle_bound=3, status="active"))
    await db.flush()

    guest = await make_account("guest", f"g-{uuid.uuid4().hex[:8]}")
    now = dt.datetime.now(dt.timezone.utc)
    original_checkout = now + dt.timedelta(days=1)
    requested_checkout = now + dt.timedelta(days=3)
    stay = Stay(guest_account_id=guest.id, room_id=room.id,
                check_in=now, check_out=original_checkout,
                status="active")
    db.add(stay)
    await db.flush()
    r = Request(guest_account_id=guest.id, stay_id=stay.id, raw_text="x")
    db.add(r)
    await db.flush()
    child = ChildSubRequest(request_id=r.id, text="extend my checkout",
                            outcome="auto", state="triaged",
                            issue_code_id=ic.id, priority_tier="P3",
                            requested_checkout=requested_checkout)
    db.add(child)
    await db.flush()

    esc = Escalation(child_id=child.id, trigger="triage_flag", state="open",
                     cycle_count=0, raised_by_account_id=None)
    db.add(esc)
    await db.flush()
    db.add(Recommendation(escalation_id=esc.id,
                          action="apply_reservation_mutation",
                          rationale_text="approve the checkout extension"))
    await db.flush()
    db.add(RecApplyReservationMutation(
        recommendation_escalation_id=esc.id, field="check_out",
        requested_value=requested_checkout))
    await db.flush()

    return {"child": child, "stay": stay, "esc": esc,
            "original_checkout": original_checkout,
            "requested_checkout": requested_checkout}


@pytest.mark.asyncio
async def test_execute_apply_mutation_changes_checkout_and_closes(
        db, make_account):
    """approve path: stay.check_out mutated, exactly one reservation_mutated
    event, child → answered (closure-lite), resolution recorded."""
    import sqlalchemy as sa
    from conduit.shared.models import (Event, EventReservationMutated,
                                       NoDispatchResolution, Stay,
                                       ChildSubRequest)

    h = await _seed_triage_mutation_scenario(db, make_account)
    actor = await make_account("supervisor", f"sup-{__import__('uuid').uuid4().hex[:8]}")

    await spine.apply_recommendation(db, h["esc"], outcome="approved",
                                     actor=actor.id)
    await db.flush()

    # Stay.check_out == the requested value.
    stay = (await db.execute(
        sa.select(Stay).where(Stay.id == h["stay"].id)
    )).scalar_one()
    assert stay.check_out == h["requested_checkout"]

    # Exactly one reservation_mutated event with correct old/new.
    evs = (await db.execute(
        sa.select(Event).where(Event.type == "reservation_mutated")
    )).scalars().all()
    assert len(evs) == 1
    detail = (await db.execute(
        sa.select(EventReservationMutated)
        .where(EventReservationMutated.event_id == evs[0].id)
    )).scalar_one()
    assert detail.stay_id == h["stay"].id
    assert detail.field == "check_out"
    assert detail.old_value == h["original_checkout"]
    assert detail.new_value == h["requested_checkout"]

    # child → answered (closure-lite).
    child = (await db.execute(
        sa.select(ChildSubRequest)
        .where(ChildSubRequest.id == h["child"].id)
    )).scalar_one()
    assert child.state == "answered"

    # A NoDispatchResolution(mode='reservation_mutation') exists for the child.
    ndr = (await db.execute(
        sa.select(NoDispatchResolution)
        .where(NoDispatchResolution.child_id == h["child"].id)
    )).scalar_one()
    assert ndr.mode == "reservation_mutation"
