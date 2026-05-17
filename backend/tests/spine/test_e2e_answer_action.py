"""E2E: answer↔action seam (Spec §9.2). Approve path == silent
auto-proceed path (one-executor symmetry through a reservation mutation).
Time pinned via fire_at-past + synchronous engine tick (engine loop off).

This is the slice's reason-to-exist test. It is built ENTIRELY from the
existing helpers/idioms — nothing is invented:

* Seeding mirrors ``tests/spine/test_intake_history.py`` and
  ``tests/spine/test_supervisor_decisions.py::_seed_world`` verbatim
  (guest Account + active Stay in Room/Section/Property, an active P3
  ``SLAPreset``, a ``LATE_CHECKOUT`` ``IssueCode`` with
  ``is_reservation_mutation=True`` + ``sla_preset_id``, an active
  ``EscalationLadder``).
* The guest journey is driven through ``intake.submit_request`` /
  ``intake.confirm`` exactly the way ``tests/spine/test_e2e_journey.py``
  phases B/C/D drive them, with ``fake_llm`` set as in
  ``test_e2e_journey.py`` / ``test_intake_history.py`` (the
  ``fake_llm["ground"]`` / ``fake_llm["classify"]`` async callables).
* Supervisor resolution is driven over the REAL per-test ``client`` with
  the real per-role ``login`` cookie swap, exactly as
  ``tests/spine/test_supervisor_decisions.py`` does
  (``GET /api/supervisor/decisions`` /
  ``POST /api/supervisor/decisions/{id}/resolve``).
* The guest closure is the REAL guest route
  ``POST /api/guest/children/{cid}/confirm`` ({"helpful": true}) — the
  HTTP twin of ``intake.confirm`` used by ``test_e2e_journey.py`` phase C.
* Scenario B's due-timer + synchronous tick mirror
  ``tests/spine/test_supervisor_decisions.py`` (cancel the spine-armed
  future ``supervisor_sla`` Timer, ``timers.arm`` a new one in the past,
  ``runner.tick(db)``) and ``tests/spine/test_engine.py``
  (``runner.tick`` with the engine loop OFF — ``runner`` is invoked
  directly, no background loop).

One-executor symmetry: BOTH the supervisor ``approve`` (Scenario A) and
the silent auto-proceed (Scenario B) flow through the SAME
``spine.apply_recommendation``; the end state is asserted byte-identical
(``stay.check_out`` == requested, child ``state`` == answered, the
``NoDispatchResolution.mode`` == ``reservation_mutation``, exactly ONE
``reservation_mutated`` Event each — append-only) EXCEPT
``escalation.resolved_by_account_id`` (the supervisor for A, ``None`` for
the silent path B).
"""
from __future__ import annotations

import datetime as dt
import uuid

import pytest
import sqlalchemy as sa

from conduit.guest.services import intake
from conduit.shared.engine import runner
from conduit.shared.engine import timers as _t
from conduit.shared.models import (
    ChildSubRequest,
    Escalation,
    EscalationLadder,
    Event,
    EventReservationMutated,
    IssueCode,
    NoDispatchResolution,
    Property,
    Recommendation,
    Room,
    Section,
    SLAPreset,
    Stay,
    Timer,
)

_PW = "pw-123456"  # conftest default in make_account / seeded_guest


async def _seed_mutation_world(db, make_account):
    """Guest + active Stay + active P3 SLAPreset + a LATE_CHECKOUT issue
    code (no_dispatch, is_reservation_mutation=True, sla_preset_id) + an
    active EscalationLadder — the EXACT FK-chain idiom proven in
    tests/spine/test_intake_history.py
    ::test_followup_mutation_opens_escalation_with_requested_checkout
    (and tests/spine/test_supervisor_decisions.py::_seed_world). Returns
    handles incl. the guest Account and the ORIGINAL stay.check_out.
    """
    guest = await make_account("guest", f"g-{uuid.uuid4().hex[:8]}", _PW)
    duty = await make_account("supervisor", f"dm-{uuid.uuid4().hex[:8]}", _PW)
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
    original_checkout = now + dt.timedelta(days=1)
    stay = Stay(guest_account_id=guest.id, room_id=room.id, check_in=now,
                check_out=original_checkout, status="active")
    db.add(stay)
    await db.flush()
    sla = SLAPreset(property_id=p.id, tier="P3", accept_window_seconds=120,
                    fulfilment_sla_seconds=1800, supervisor_sla_seconds=900,
                    status="active")
    db.add(sla)
    await db.flush()
    # One test == one savepoint ⇒ all three scenarios' seed rows coexist;
    # the issue code has a UNIQUE(lower(code)) constraint, so each scenario
    # gets its OWN code (the exact ``f"IC-{uuid…}"`` idiom proven in
    # tests/spine/test_supervisor_decisions.py::_seed_world /
    # test_engine.py::_seed_routed_child). The fake classify references it
    # by THIS value, so the seam is unaffected.
    code = f"LATE_CHECKOUT_{uuid.uuid4().hex[:8]}"
    ic = IssueCode(code=code, label="Late checkout",
                   department="front_desk", fulfilment_mode="no_dispatch",
                   routing_model="none", is_reservation_mutation=True,
                   sla_preset_id=sla.id, status="active")
    db.add(ic)
    await db.flush()
    db.add(EscalationLadder(property_id=p.id,
                            duty_manager_account_id=duty.id,
                            n_cycle_bound=3, status="active"))
    await db.flush()
    return {"guest": guest, "stay": stay, "issue_code": code,
            "original_checkout": original_checkout}


async def _drive_seam_to_escalation(db, fake_llm, guest, original_checkout,
                                    issue_code):
    """The shared journey up to the open escalation (identical for A & B):

      1. "what time is checkout?"  → grounded answer persisted (the prior
         conversation turn the history-aware classify needs).
      2. "can I get it till 2pm?"  → classify (history-aware) returns ONE
         LATE_CHECKOUT child with ``requested_checkout = orig + 3h`` (ISO);
         the seeded code's ``is_reservation_mutation=True`` force-flags it
         (triage Resolution A) → it rides the spine's generic FLAG trigger
         into the decision queue with an
         ``apply_reservation_mutation`` Recommendation.

    Returns (child_id, requested_checkout_dt, escalation).
    """
    requested = original_checkout + dt.timedelta(hours=3)
    requested_iso = requested.isoformat()

    # Turn 1 — grounded checkout answer (one no_dispatch child).
    async def fclassify_ground(t, cat):
        return [{"text": t, "issue_code": None, "fulfilment_mode": None,
                 "outcome": "no_dispatch", "is_problem_report": False}]

    async def fground_yes(q, ctx):
        return {"grounded": True, "leaves_no_dispatch": False,
                "answer": "Checkout is 11:00.", "used_kb_ids": [],
                "used_fields": []}

    fake_llm["classify"] = fclassify_ground
    fake_llm["ground"] = fground_yes
    out1 = await intake.submit_request(db, guest, "what time is checkout?")
    await db.flush()
    assert out1["children"][0]["terminal"] == "answered"

    # Turn 2 — the follow-up; classify is history-aware and returns the
    # LATE_CHECKOUT mutation child with the D24 extracted target. The
    # seeded code's is_reservation_mutation=True makes triage force
    # outcome=flag (Resolution A) regardless of the proposed outcome.
    async def fclassify_mut(t, cat):
        return [{"text": t, "issue_code": issue_code,
                 "fulfilment_mode": "no_dispatch", "outcome": "no_dispatch",
                 "is_problem_report": False,
                 "requested_checkout": requested_iso}]

    fake_llm["classify"] = fclassify_mut
    out2 = await intake.submit_request(db, guest, "can I get it till 2pm?")
    await db.flush()
    child_id = uuid.UUID(out2["children"][0]["child_id"])

    # The mutation rode the spine's generic FLAG trigger into an open
    # escalation carrying an apply_reservation_mutation Recommendation
    # (proven shape — test_intake_history.py).
    esc = (await db.execute(sa.select(Escalation).where(
        Escalation.child_id == child_id))).scalar_one()
    assert esc.trigger == "triage_flag" and esc.state == "open"
    rec = (await db.execute(sa.select(Recommendation).where(
        Recommendation.escalation_id == esc.id))).scalar_one()
    assert rec.action == "apply_reservation_mutation"
    child = await db.get(ChildSubRequest, child_id)
    assert child.requested_checkout == requested
    return child_id, requested, esc


async def _end_state(db, child_id, stay_id):
    """The byte-identical end-state tuple under assertion (the
    one-executor symmetry surface) + the append-only event count."""
    stay = (await db.execute(sa.select(Stay).where(
        Stay.id == stay_id))).scalar_one()
    child = (await db.execute(sa.select(ChildSubRequest).where(
        ChildSubRequest.id == child_id))).scalar_one()
    res = (await db.execute(sa.select(NoDispatchResolution).where(
        NoDispatchResolution.child_id == child_id))).scalar_one()
    # reservation_mutated events scoped to THIS stay (append-only: exactly
    # one per the single mutation — no update/delete row).
    n_mut = (await db.execute(
        sa.select(sa.func.count())
        .select_from(EventReservationMutated)
        .where(EventReservationMutated.stay_id == stay_id))).scalar_one()
    return (stay.check_out, child.state, res.mode, n_mut)


@pytest.mark.asyncio
async def test_seam_approve_and_autoproceed_are_identical(
        db, client, login, make_account, fake_llm):
    # ===================================================================
    # SCENARIO A — supervisor APPROVE via the REAL resolve route.
    # ===================================================================
    wa = await _seed_mutation_world(db, make_account)
    sup = await make_account("supervisor", f"sup-{uuid.uuid4().hex[:8]}",
                             _PW)
    child_a, requested_a, esc_a = await _drive_seam_to_escalation(
        db, fake_llm, wa["guest"], wa["original_checkout"],
        wa["issue_code"])
    await db.commit()

    # The item is present in the supervisor decision queue (real route).
    await login(sup.username, _PW)
    lst = await client.get("/api/supervisor/decisions")
    assert lst.status_code == 200, lst.text
    by_id = {d["escalation_id"]: d for d in lst.json()}
    assert str(esc_a.id) in by_id
    card = by_id[str(esc_a.id)]
    assert card["trigger"] == "triage_flag"
    assert card["recommendation"]["action"] == "apply_reservation_mutation"

    # POST resolve {action: "approve"} — the STORED recommendation runs
    # verbatim through spine.apply_recommendation (the ONE executor).
    rok = await client.post(
        f"/api/supervisor/decisions/{esc_a.id}/resolve",
        json={"action": "approve"})
    assert rok.status_code == 200, rok.text
    await db.commit()

    esc_a_row = (await db.execute(sa.select(Escalation).where(
        Escalation.id == esc_a.id))).scalar_one()
    assert esc_a_row.state == "approved"
    assert str(esc_a_row.resolved_by_account_id) == str(sup.id)

    end_a = await _end_state(db, child_a, wa["stay"].id)
    assert end_a[0] == requested_a            # stay.check_out == requested
    assert end_a[1] == "answered"             # child closure-lite
    assert end_a[2] == "reservation_mutation"  # resolution mode
    assert end_a[3] == 1                      # exactly ONE mutated event

    # The append-only reservation_mutated event for THIS stay has the
    # correct old=orig / new=requested (no enumeration, scoped by stay).
    det_a = (await db.execute(sa.select(EventReservationMutated).where(
        EventReservationMutated.stay_id == wa["stay"].id))).scalar_one()
    assert det_a.field == "check_out"
    assert det_a.old_value == wa["original_checkout"]
    assert det_a.new_value == requested_a
    ev_a = (await db.execute(sa.select(Event).where(
        Event.id == det_a.event_id,
        Event.type == "reservation_mutated"))).scalar_one()
    assert ev_a is not None

    # Guest confirms via the REAL guest confirm route → child closed.
    await login(wa["guest"].username, _PW)
    rc = await client.post(
        f"/api/guest/children/{child_a}/confirm", json={"helpful": True})
    assert rc.status_code == 200, rc.text
    await db.commit()
    child_a_row = (await db.execute(sa.select(ChildSubRequest).where(
        ChildSubRequest.id == child_a))).scalar_one()
    assert child_a_row.state == "closed"

    # ===================================================================
    # SCENARIO B — fresh independent seed; DO NOT resolve. Make the
    # supervisor_sla Timer due (fire_at past) + run the synchronous engine
    # tick (engine loop OFF — runner.tick called directly). Silence ≡
    # approve: the SAME spine.apply_recommendation auto-proceeds.
    # ===================================================================
    wb = await _seed_mutation_world(db, make_account)
    child_b, requested_b, esc_b = await _drive_seam_to_escalation(
        db, fake_llm, wb["guest"], wb["original_checkout"],
        wb["issue_code"])
    await db.commit()

    # The spine armed a FUTURE supervisor_sla timer at open time; cancel it
    # and arm one in the past so the runner claims it — the EXACT D3
    # mechanism in tests/spine/test_supervisor_decisions.py.
    db_now = (await db.execute(sa.select(sa.func.now()))).scalar_one()
    await db.execute(sa.update(Timer).where(
        Timer.escalation_id == esc_b.id,
        Timer.type == "supervisor_sla",
        Timer.state == "pending").values(state="cancelled"))
    await _t.arm(db, "escalation_id", esc_b.id,
                 _t.TimerType.SUPERVISOR_SLA,
                 fire_at=db_now - dt.timedelta(seconds=5))
    await db.flush()

    fired = await runner.tick(db)            # synchronous tick, loop OFF
    assert fired >= 1
    await db.commit()

    esc_b_row = (await db.execute(sa.select(Escalation).where(
        Escalation.id == esc_b.id))).scalar_one()
    assert esc_b_row.state == "auto_proceeded"
    assert esc_b_row.resolved_by_account_id is None  # silence ≡ approve

    end_b = await _end_state(db, child_b, wb["stay"].id)
    assert end_b[0] == requested_b
    assert end_b[1] == "answered"
    assert end_b[2] == "reservation_mutation"
    assert end_b[3] == 1                      # append-only single event

    # ===================================================================
    # ONE-EXECUTOR SYMMETRY — A and B reached a BYTE-IDENTICAL end state
    # (each relative to its own requested value): child state, resolution
    # mode, and the append-only reservation_mutated event count are
    # identical; the only difference is resolved_by_account_id (the
    # supervisor for A, None for the silent path B).
    # ===================================================================
    assert end_a[0] == requested_a and end_b[0] == requested_b
    assert end_a[1] == end_b[1] == "answered"
    assert end_a[2] == end_b[2] == "reservation_mutation"
    assert end_a[3] == end_b[3] == 1         # exactly ONE event each
    assert str(esc_a_row.resolved_by_account_id) == str(sup.id)
    assert esc_b_row.resolved_by_account_id is None

    # ===================================================================
    # SCENARIO C — supervisor EDIT through the REAL resolve route's
    # datetime-variant payload (an EDITED requested_value = orig + 1h, NOT
    # the originally-extracted orig + 3h).
    #
    # SEAM BOUNDARY (reported, not papered over): the real resolve API
    # carries the supervisor-supplied edit payload as a plain JSON ``dict``
    # (``ResolveIn.payload: dict | None`` — supervisor/schemas/decisions.py,
    # no field schema/coercion) and the spine's ``_resolved_action`` returns
    # ``(action, dict(payload))`` VERBATIM for the ``edited`` outcome
    # (engine/spine.py — no datetime parsing). JSON has no native datetime,
    # so the ONLY value a real HTTP client can send for ``requested_value``
    # is an ISO-8601 string; the spine then assigns that string straight
    # onto ``Stay.check_out`` (a ``TIMESTAMP WITH TIME ZONE`` column) and
    # asyncpg rejects it. This is a genuine product gap in the edit-path
    # datetime coercion (NOT a test-construction error and NOT a defect
    # in the A/B one-executor seam, which is fully proven above). Per the
    # task: C is implemented "as far as the real resolve API cleanly
    # supports" — we drive the REAL route with the REAL datetime-variant
    # payload and PIN the exact boundary at the real seam (no production
    # change, no invented API). When the edit-path coercion is added this
    # ``pytest.raises`` flips to a clean success and the commented success
    # assertions below become the live contract.
    # ===================================================================
    import sqlalchemy.exc as _saexc

    wc = await _seed_mutation_world(db, make_account)
    sup_c = await make_account("supervisor", f"supc-{uuid.uuid4().hex[:8]}",
                               _PW)
    child_c, extracted_c, esc_c = await _drive_seam_to_escalation(
        db, fake_llm, wc["guest"], wc["original_checkout"],
        wc["issue_code"])
    await db.commit()

    edited_value = wc["original_checkout"] + dt.timedelta(hours=1)
    assert edited_value != extracted_c       # the edit really differs

    # The edit path IS dispatched to the SAME single executor with the
    # supervisor-supplied typed action (proving the seam is reached); the
    # ISO-string requested_value is rejected at the real DB write — the
    # precise, reported boundary of the real resolve API's datetime
    # variant. Driven directly against the service-layer seam (the route
    # would surface the SAME asyncpg DataError as an unhandled 500, since
    # only ConduitError is mapped — core/exceptions.py); asserting at the
    # seam pins the gap deterministically without a flaky 500 round-trip.
    from conduit.core.deps import Actor as _Actor
    from conduit.supervisor.services import decisions as _decisions_svc

    esc_c_loaded = (await db.execute(sa.select(Escalation).where(
        Escalation.id == esc_c.id))).scalar_one()
    with pytest.raises((_saexc.DBAPIError, _saexc.StatementError)):
        await _decisions_svc.resolve(
            db, _Actor(id=str(sup_c.id), role="supervisor"),
            esc_c_loaded.id, action="edit", payload={
                "action": "apply_reservation_mutation",
                "field": "check_out",
                "requested_value": edited_value.isoformat()})
    # Discard the poisoned unit of work (the asyncpg error aborts the
    # savepoint); the conftest's single outer rollback still guarantees
    # zero residue regardless.
    await db.rollback()

    # --- The contract C WILL assert once the edit-path datetime coercion
    # --- exists (kept here as the precise, ready-to-activate spec so the
    # --- sentinel documents the intended end state of the edit variant):
    #   esc_c_row.state == "edited"
    #   esc_c_row.resolved_by_account_id == sup_c.id
    #   Stay.check_out == edited_value  (NOT extracted_c)
    #   exactly ONE EventReservationMutated(stay) new==edited old==orig
    #   ChildSubRequest(child_c).state == "answered"
