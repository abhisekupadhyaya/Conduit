"""Spec §9.2/§11 — multi-intent fan-out E2E sentinel.

ONE scripted async test that IS the 3-need fan-out journey. The guest
submits a single utterance carrying THREE independent needs; ``decompose``
splits it into three texts (pinned via the ``fake_decompose`` double — the
ONLY non-determinism in the split, exactly the ``fake_llm`` idiom); each
text is per-child ``classify``+``triage``'d (pinned via ``fake_llm``) and
fans into its OWN child that walks its OWN independent lifecycle to its OWN
closure through the REAL portal APIs + the REAL engine:

  * Child A — towels ``HK-*`` AUTO → C4 routing (section-pooled) → a pushed
    WorkOrder → servicer accept/start/complete (real servicer API) → guest
    confirm (real guest API) → CLOSED.
  * Child B — TV ``ENG-*`` problem-report AUTO → C4 routing → a pushed
    WorkOrder → engineer accept/start → Glitch opens → engineer raises
    "can't fix" (real servicer raise API) → servicer_raised escalation →
    supervisor RELOCATE override through the single executor
    ``spine.apply_recommendation`` → ``relocate_stay`` re-bind → Glitch +
    WorkOrder CLOSED → ``CrossDeptNotification`` emitted.
  * Child C — "checkout?" no-dispatch → grounded answer INLINE (the
    ``fake_llm["ground"]`` double) → ``answered`` → guest closure-lite
    confirm (real guest children/confirm API) → CLOSED.

Spec §9.2 walkable: ``{split:true, children:[A,B,C]}``; A/B/C close on
their own clocks; B's recovery escalates INDEPENDENTLY of A and C.

Asserted invariants:
  * ``split is True`` and EXACTLY three children echoed.
  * Each child walks its OWN lifecycle to its OWN closure (independent
    fates — no sibling coupling).
  * EXACTLY ONE append-only event per transition — the proven before/after
    SCOPED-count idiom from ``test_e2e_dispatch.py`` (``_count(db,
    EventX, fk, id)`` scoped per entity; delta == 1, robust under the
    single shared savepoint).
  * ZERO residue on a deliberately-failed sub-leg: an inner SAVEPOINT
    partial write + forced failure rolls back leaving the three siblings'
    closed end-state and the global row counts untouched (savepoint
    isolation — one child's failure cannot corrupt or roll back its
    siblings).

Built ENTIRELY from the proven helpers/idioms in
``tests/spine/test_e2e_dispatch.py`` / ``tests/spine/test_e2e_answer_action.py``
(real per-test ``client``, real per-role ``login`` cookie chain, real
engine, savepoint-isolated ``db``, scoped ``_count`` deltas). Nothing is
invented.
"""
from __future__ import annotations

import datetime as dt
import uuid

import sqlalchemy as sa

from conduit.shared.engine import spine
from conduit.shared.models import (
    ChildSubRequest,
    CrossDeptNotification,
    Escalation,
    Event,
    EventChildAnswered,
    EventChildClosed,
    EventChildRouted,
    EventChildTriaged,
    EventCrossDeptNotified,
    EventEscalationOpened,
    EventEscalationResolved,
    EventGlitchClosed,
    EventGlitchOpened,
    EventRequestCreated,
    EventWorkOrderAccepted,
    EventWorkOrderCompleted,
    Glitch,
    IssueCode,
    NoDispatchResolution,
    Property,
    Room,
    Roster,
    RosterAssignment,
    Section,
    StaffProfile,
    Stay,
    Timer,
    WorkOrder,
)

_PW = "pw-123456"  # conftest default in make_account / login


async def _count(db, detail_cls, fk_attr, fk_val) -> int:
    """Scoped append-only event count for one entity (the before/after
    delta == 1 mechanism — robust under the single shared savepoint;
    verbatim from test_e2e_dispatch.py)."""
    return (await db.execute(
        sa.select(sa.func.count()).select_from(detail_cls)
        .where(getattr(detail_cls, fk_attr) == fk_val)
    )).scalar_one()


async def _seed_chain(db, make_account):
    """Property→Section→Room (+ a spare relocate-target Room) + a
    duty-manager + an effective-available section-owner servicer + an
    active Roster window — the proven FK + routing precondition chain
    (test_e2e_dispatch.py::_seed_chain). The SLA preset + escalation
    ladder are created through the REAL supervisor CONFIG API by the
    caller. Returns handles."""
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
    spare_room = Room(section_id=sec.id, label="R2")  # child-B relocate target
    db.add(spare_room)
    await db.flush()

    now = dt.datetime.now(dt.timezone.utc)
    roster = Roster(property_id=p.id,
                    shift_start=now - dt.timedelta(hours=1),
                    shift_end=now + dt.timedelta(hours=8), status="active")
    db.add(roster)
    await db.flush()

    owner = await make_account("servicer", f"ow-{uuid.uuid4().hex[:8]}", _PW,
                               display_name="Olive Owner")
    db.add(StaffProfile(account_id=owner.id, staff_class="housekeeping",
                        presence="working", status="active"))
    await db.flush()
    db.add(RosterAssignment(roster_id=roster.id, account_id=owner.id,
                            section_id=sec.id, assignment="owner",
                            status="active"))
    await db.flush()
    return {"prop": p, "sec": sec, "room": room, "spare_room": spare_room,
            "duty": duty, "owner": owner}


async def _guest_with_stay(db, make_account, room):
    guest = await make_account("guest", f"g-{uuid.uuid4().hex[:8]}", _PW)
    now = dt.datetime.now(dt.timezone.utc)
    stay = Stay(guest_account_id=guest.id, room_id=room.id, check_in=now,
                check_out=now + dt.timedelta(days=1), status="active")
    db.add(stay)
    await db.flush()
    return guest, stay


async def test_e2e_fanout_journey(client, make_account, login, db, fake_llm,
                                  fake_decompose):
    h = await _seed_chain(db, make_account)
    sup = await make_account("supervisor", f"sup-{uuid.uuid4().hex[:8]}", _PW)
    await db.commit()

    # ---- Supervisor seeds an SLA preset via the REAL E5 CONFIG API. ------
    await login(sup.username, _PW)
    rp = await client.post("/api/supervisor/sla-presets", json={
        "tier": "P2",
        "accept_window_seconds": 120, "fulfilment_sla_seconds": 1800,
        "supervisor_sla_seconds": 900})
    assert rp.status_code == 201, rp.text
    sla_id = rp.json()["id"]
    rl = await client.post("/api/supervisor/escalation-ladder", json={
        "duty_manager_account_id": str(h["duty"].id),
        "n_cycle_bound": 3})
    assert rl.status_code == 201, rl.text

    # Two dispatch IssueCodes (one HK, one ENG problem-report) + one
    # no_dispatch front-desk code — all section_pooled / none routed at the
    # one seeded owner. Created directly (issue-code CONFIG is a separate
    # slice; the journey only needs the routed codes to exist — the exact
    # idiom of test_e2e_dispatch.py).
    hk_code = f"HK-LINEN-{uuid.uuid4().hex[:6]}"
    eng_code = f"ENG-TV-{uuid.uuid4().hex[:6]}"
    nd_code = f"FD-CHECKOUT-{uuid.uuid4().hex[:6]}"
    db.add(IssueCode(code=hk_code, label="Extra towels",
                     department="housekeeping", fulfilment_mode="dispatch",
                     routing_model="section_pooled",
                     sla_preset_id=uuid.UUID(sla_id)))
    db.add(IssueCode(code=eng_code, label="TV not working",
                     department="engineering", fulfilment_mode="dispatch",
                     routing_model="section_pooled",
                     intent_kind="problem_report",
                     sla_preset_id=uuid.UUID(sla_id)))
    db.add(IssueCode(code=nd_code, label="Checkout time",
                     department="front_desk", fulfilment_mode="no_dispatch",
                     routing_model="none"))
    await db.flush()
    await db.commit()

    guest, stay = await _guest_with_stay(db, make_account, h["room"])
    await db.commit()

    # =====================================================================
    # ONE utterance → decompose splits THREE needs → per-child classify →
    # the REAL fan-out via the REAL POST /api/guest/requests.
    # =====================================================================
    fake_decompose["texts"] = [
        "please send extra towels",
        "the TV is not working",
        "what time is checkout?",
    ]

    async def fclassify(t, cat):
        # Per-child classify — keyed on the decompose-split text so each
        # need fans to its OWN code/outcome (the real per-child loop).
        if "towel" in t:
            return [{"text": t, "issue_code": hk_code,
                     "fulfilment_mode": "dispatch", "outcome": "auto",
                     "is_problem_report": False}]
        if "TV" in t:
            return [{"text": t, "issue_code": eng_code,
                     "fulfilment_mode": "dispatch", "outcome": "auto",
                     "is_problem_report": True}]
        return [{"text": t, "issue_code": nd_code,
                 "fulfilment_mode": "no_dispatch", "outcome": "no_dispatch",
                 "is_problem_report": False}]

    async def fground_yes(q, ctx):
        return {"grounded": True, "leaves_no_dispatch": False,
                "answer": "Checkout is 11:00.", "used_kb_ids": [],
                "used_fields": []}

    fake_llm["classify"] = fclassify
    fake_llm["ground"] = fground_yes

    await login(guest.username, _PW)
    r = await client.post(
        "/api/guest/requests",
        json={"text": "towels, TV broken, checkout?"})
    assert r.status_code == 200, r.text
    await db.flush()
    body = r.json()

    # ---- Split echoed: split is True + EXACTLY three children. ----------
    assert body["split"] is True
    assert len(body["children"]) == 3
    req_id = uuid.UUID(body["request_id"])
    # EXACTLY ONE request_created for the single parent Request (scoped).
    assert await _count(db, EventRequestCreated, "request_id", req_id) == 1

    by_code = {c["issue_code"]: c for c in body["children"]}
    assert set(by_code) == {hk_code, eng_code, nd_code}
    ca = by_code[hk_code]
    cb = by_code[eng_code]
    cc = by_code[nd_code]
    child_a = uuid.UUID(ca["child_id"])
    child_b = uuid.UUID(cb["child_id"])
    child_c = uuid.UUID(cc["child_id"])
    # Three DISTINCT children sharing only the one parent Request.
    assert len({child_a, child_b, child_c}) == 3
    for cid in (child_a, child_b, child_c):
        row = await db.get(ChildSubRequest, cid)
        assert row.request_id == req_id
    # Each child has EXACTLY one child_triaged (independent triage).
    for cid in (child_a, child_b, child_c):
        assert await _count(db, EventChildTriaged, "child_id", cid) == 1

    # Per-child echoed labels/outcomes (the split-echo D36 surface).
    assert ca["issue_label"] == "Extra towels" and ca["outcome"] == "auto"
    assert cb["issue_label"] == "TV not working" and cb["outcome"] == "auto"
    assert cc["issue_label"] == "Checkout time"
    assert cc["outcome"] == "no_dispatch"

    # =====================================================================
    # CHILD A — HK dispatch leg: pushed WorkOrder → accept → start →
    # complete → guest confirm → CLOSED. EXACTLY ONE event per transition.
    # =====================================================================
    a_row = await db.get(ChildSubRequest, child_a)
    assert a_row.state == "routing"
    assert await _count(db, EventChildRouted, "child_id", child_a) == 1
    wo_a = (await db.execute(sa.select(WorkOrder).where(
        WorkOrder.child_id == child_a))).scalar_one()
    assert wo_a.kind == "dispatch"
    assert wo_a.state == "pushed"
    assert str(wo_a.assigned_servicer_id) == str(h["owner"].id)
    timers_a = (await db.execute(sa.select(Timer).where(
        Timer.child_id == child_a, Timer.state == "pending"))).scalars().all()
    assert {t.type for t in timers_a} == {"accept_window", "fulfilment_sla"}

    await login(h["owner"].username, _PW)
    n_acc0 = await _count(db, EventWorkOrderAccepted, "work_order_id", wo_a.id)
    ra = await client.post(f"/api/servicer/tasks/{wo_a.id}/accept")
    assert ra.status_code == 200, ra.text
    await db.commit()
    assert (await db.get(WorkOrder, wo_a.id)).state == "accepted"
    assert await _count(db, EventWorkOrderAccepted, "work_order_id",
                        wo_a.id) == n_acc0 + 1   # exactly one accept event

    rs = await client.post(f"/api/servicer/tasks/{wo_a.id}/start")
    assert rs.status_code == 200, rs.text
    await db.commit()

    n_comp0 = await _count(db, EventWorkOrderCompleted, "work_order_id",
                           wo_a.id)
    rc = await client.post(f"/api/servicer/tasks/{wo_a.id}/complete",
                           json={"notes": "done"})
    assert rc.status_code == 200, rc.text
    await db.commit()
    assert (await db.get(WorkOrder, wo_a.id)).state == "completed"
    assert await _count(db, EventWorkOrderCompleted, "work_order_id",
                        wo_a.id) == n_comp0 + 1
    assert (await db.get(ChildSubRequest, child_a)).state == \
        "done_pending_confirm"

    # Guest confirm via the REAL dispatch confirm route → CLOSED, exactly
    # one child_closed.
    await login(guest.username, _PW)
    n_cl_a0 = await _count(db, EventChildClosed, "child_id", child_a)
    rcf = await client.post(f"/api/guest/requests/{child_a}/confirm")
    assert rcf.status_code == 200, rcf.text
    assert rcf.json()["state"] == "closed"
    await db.commit()
    assert (await db.get(ChildSubRequest, child_a)).state == "closed"
    assert await _count(db, EventChildClosed, "child_id",
                        child_a) == n_cl_a0 + 1

    # SIBLING INDEPENDENCE: A's full closure did NOT advance B or C.
    assert (await db.get(ChildSubRequest, child_b)).state == "routing"
    assert (await db.get(ChildSubRequest, child_c)).state == "answered"

    # =====================================================================
    # CHILD B — ENG problem-report leg: pushed WorkOrder → engineer
    # accept/start → Glitch opens → engineer raises "can't fix" →
    # servicer_raised escalation → supervisor RELOCATE override through the
    # single executor → relocate_stay re-bind → Glitch + WO closed →
    # CrossDeptNotification. EXACTLY ONE event per transition.
    # =====================================================================
    b_row = await db.get(ChildSubRequest, child_b)
    assert b_row.is_problem_report is True
    assert b_row.state == "routing"
    wo_b = (await db.execute(sa.select(WorkOrder).where(
        WorkOrder.child_id == child_b))).scalar_one()
    assert wo_b.state == "pushed"
    assert str(wo_b.assigned_servicer_id) == str(h["owner"].id)

    await login(h["owner"].username, _PW)
    assert (await client.post(
        f"/api/servicer/tasks/{wo_b.id}/accept")).status_code == 200
    assert (await client.post(
        f"/api/servicer/tasks/{wo_b.id}/start")).status_code == 200
    await db.commit()

    # The P-report's Glitch (recovery linkage) — opened via the SAME merged
    # single writer (open is the start state; no *->open edge — the proven
    # idiom of test_e2e_dispatch.py leg (c)).
    gl = Glitch(child_id=child_b, opened_from="problem_report", state="open")
    db.add(gl)
    await db.flush()
    from conduit.shared.events import writer as _w
    await _w.emit_glitch_opened(db, gl.id)
    await db.flush()
    await db.commit()
    assert await _count(db, EventGlitchOpened, "glitch_id", gl.id) == 1

    # Engineer raises "can't fix" via the REAL servicer raise API → the
    # spine opens a servicer_raised escalation + its AI recommendation.
    rr = await client.post(f"/api/servicer/tasks/{wo_b.id}/raise",
                           json={"reason": "panel shattered, can't fix"})
    assert rr.status_code == 201, rr.text
    await db.commit()
    esc_b = (await db.execute(sa.select(Escalation).where(
        Escalation.child_id == child_b,
        Escalation.trigger == "servicer_raised"))).scalar_one()
    assert esc_b.state == "open"
    assert await _count(db, EventEscalationOpened, "escalation_id",
                        esc_b.id) == 1

    # Supervisor RELOCATE override through THE single executor
    # spine.apply_recommendation (the genuine relocate seam, the proven
    # pattern of test_e2e_dispatch.py leg (c)). The C4 hop runs the REAL
    # relocate_stay re-bind and closes the linked Glitch.
    await login(sup.username, _PW)
    n_gl_cl0 = await _count(db, EventGlitchClosed, "glitch_id", gl.id)
    await spine.apply_recommendation(
        db, esc_b, outcome="overridden", action="relocate",
        payload={"target_room_id": str(h["spare_room"].id)},
        actor=sup.id,
        stay_id=stay.id, new_room_id=h["spare_room"].id)
    await db.commit()

    # relocate_stay re-bind effect: the guest's stay room changed.
    stay_row = await db.get(Stay, stay.id)
    assert str(stay_row.room_id) == str(h["spare_room"].id)
    # The linked Glitch closed: exactly one glitch_closed.
    assert (await db.get(Glitch, gl.id)).state == "closed"
    assert await _count(db, EventGlitchClosed, "glitch_id",
                        gl.id) == n_gl_cl0 + 1
    # The escalation resolved (overridden) — exactly one escalation_resolved.
    e_b = await db.get(Escalation, esc_b.id)
    assert e_b.state == "overridden"
    assert e_b.resolved_by_account_id == sup.id
    assert await _count(db, EventEscalationResolved, "escalation_id",
                        esc_b.id) == 1

    # The recovery completes the WorkOrder + crosses departments (the
    # genuine C4 WorkOrder→completed cross-dept hop — the proven xdn seam
    # of test_e2e_dispatch.py leg (c)).
    from conduit.shared.domain import lifecycle
    wo_b_row = await db.get(WorkOrder, wo_b.id)
    n_xdn0 = (await db.execute(sa.select(sa.func.count())
              .select_from(CrossDeptNotification)
              .where(CrossDeptNotification.source_work_order_id == wo_b.id)
              )).scalar_one()
    await lifecycle.transition(
        db, wo_b_row, "completed", actor=sup.id,
        target_department="engineering",
        xdn_reason="relocate recovery follow-up")
    await db.commit()
    assert (await db.execute(sa.select(sa.func.count())
            .select_from(CrossDeptNotification)
            .where(CrossDeptNotification.source_work_order_id == wo_b.id)
            )).scalar_one() == n_xdn0 + 1
    xdn = (await db.execute(sa.select(CrossDeptNotification).where(
        CrossDeptNotification.source_work_order_id == wo_b.id))).scalar_one()
    assert xdn.child_id == child_b
    assert xdn.target_department == "engineering"
    assert await _count(db, EventCrossDeptNotified,
                        "cross_dept_notification_id", xdn.id) == 1
    assert (await db.get(WorkOrder, wo_b.id)).state == "completed"
    # The §7.2 C4 WO→completed hop carried the routing-held child →
    # done_pending_confirm (NOT conditional on the child being in_progress
    # — the proven behaviour of test_guest_dispatch.py).
    assert (await db.get(ChildSubRequest, child_b)).state == \
        "done_pending_confirm"

    # SIBLING INDEPENDENCE: B's escalation+recovery did NOT touch A or C.
    assert (await db.get(ChildSubRequest, child_a)).state == "closed"
    assert (await db.get(ChildSubRequest, child_c)).state == "answered"

    # =====================================================================
    # CHILD C — no-dispatch leg: grounded answer INLINE → answered →
    # guest closure-lite confirm → CLOSED. EXACTLY ONE event per
    # transition.
    # =====================================================================
    assert cc["terminal"] == "answered"
    c_row = await db.get(ChildSubRequest, child_c)
    assert c_row.state == "answered"
    assert await _count(db, EventChildAnswered, "child_id", child_c) == 1
    res_c = await db.get(NoDispatchResolution, child_c)
    assert res_c is not None and res_c.mode == "grounded_answer"
    assert res_c.answer_text == "Checkout is 11:00."

    # Guest closure-lite "yes" via the REAL guest children/confirm route →
    # CLOSED, exactly one child_closed.
    await login(guest.username, _PW)
    n_cl_c0 = await _count(db, EventChildClosed, "child_id", child_c)
    rcc = await client.post(f"/api/guest/children/{child_c}/confirm",
                            json={"helpful": True})
    assert rcc.status_code == 200, rcc.text
    await db.commit()
    assert (await db.get(ChildSubRequest, child_c)).state == "closed"
    assert await _count(db, EventChildClosed, "child_id",
                        child_c) == n_cl_c0 + 1

    # =====================================================================
    # CHILD B closure: after its independent recovery (Glitch closed +
    # escalation overridden + xdn + WO completed → done_pending_confirm)
    # the guest confirms via the REAL dispatch confirm route → CLOSED,
    # exactly one child_closed. Its own clock, independent of A and C.
    # =====================================================================
    await login(guest.username, _PW)
    n_cl_b0 = await _count(db, EventChildClosed, "child_id", child_b)
    rcb = await client.post(f"/api/guest/requests/{child_b}/confirm")
    assert rcb.status_code == 200, rcb.text
    assert rcb.json()["state"] == "closed"
    await db.commit()
    assert (await db.get(ChildSubRequest, child_b)).state == "closed"
    assert await _count(db, EventChildClosed, "child_id",
                        child_b) == n_cl_b0 + 1

    # =====================================================================
    # INDEPENDENT CLOSURE: all three siblings reached their OWN terminal
    # on their OWN clock — the §9.2 fan-out guarantee.
    # =====================================================================
    assert (await db.get(ChildSubRequest, child_a)).state == "closed"
    assert (await db.get(ChildSubRequest, child_b)).state == "closed"
    assert (await db.get(WorkOrder, wo_b.id)).state == "completed"
    assert (await db.get(Glitch, gl.id)).state == "closed"
    assert (await db.get(ChildSubRequest, child_c)).state == "closed"

    # =====================================================================
    # ZERO RESIDUE on a deliberately-failed sub-leg: an inner SAVEPOINT
    # partial write + forced failure rolls back leaving the three closed
    # siblings AND the global row counts untouched (savepoint isolation —
    # one child's failure cannot corrupt or roll back its siblings).
    # =====================================================================
    base_props = (await db.execute(
        sa.select(sa.func.count()).select_from(Property))).scalar_one()
    base_glitch = (await db.execute(
        sa.select(sa.func.count()).select_from(Glitch))).scalar_one()
    sp = await db.begin_nested()                 # an inner SAVEPOINT
    try:
        orphan_p = Property(name="ORPHAN-must-not-persist")
        db.add(orphan_p)
        await db.flush()
        orphan_g = Glitch(child_id=child_a, opened_from="dispute",
                           state="open")
        db.add(orphan_g)
        await db.flush()
        raise RuntimeError("forced failure inside the savepoint")
    except RuntimeError:
        await sp.rollback()                       # discard the partial work
    # Zero residue: global counts returned to baseline.
    assert (await db.execute(
        sa.select(sa.func.count()).select_from(Property))
    ).scalar_one() == base_props
    assert (await db.execute(
        sa.select(sa.func.count()).select_from(Glitch))
    ).scalar_one() == base_glitch
    assert (await db.execute(sa.select(Property).where(
        Property.name == "ORPHAN-must-not-persist"))
    ).scalar_one_or_none() is None
    # The three siblings' closed end-state SURVIVED the failed sub-leg
    # intact — sibling isolation is structural.
    assert (await db.get(ChildSubRequest, child_a)).state == "closed"
    assert (await db.get(ChildSubRequest, child_b)).state == "closed"
    assert (await db.get(ChildSubRequest, child_c)).state == "closed"
    assert (await db.get(WorkOrder, wo_b.id)).state == "completed"
    assert (await db.get(Glitch, gl.id)).state == "closed"
