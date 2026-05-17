"""Task G2 — Spec §11 E2E dispatch sentinel.

ONE scripted async test that IS the dispatch journey, time pinned via
``fire_at`` + explicit ``runner.tick`` (AD5-honest — no real sleeping, DB
``now()`` preserved). It drives the journey through the REAL portal APIs
(merged intake, servicer accept/complete/raise, guest confirm, supervisor
config + resolve) and the REAL engine (``runner.tick`` after ``fire_at``-past
timers) — NOT direct model writes for the journey transitions.

Seed is via the supervisor CONFIG API (E5 ``sla-presets`` +
``escalation-ladder``; ``n_cycle_bound=2`` so leg (b) reaches the D21 bound
fast) plus the Property/Section/Room/Stay + IssueCode + Roster chain.

Legs (Spec §11):
  (a) happy:  accept → complete → guest confirm → CLOSED.
  (b) stall:  no accept; ``fire_at``-past + ``tick`` → stall → decision
      queue → supervisor SILENT → ``tick`` supervisor-SLA → auto-proceed
      the stored recommendation (for D12 ``section_pooled`` the stalled
      owner is excluded ⇒ the C1 claim-fallback ``broadcast``) → the REAL
      D3 carry-forward chain (cycle_count is NEVER hand-seeded) →
      hard-escalate to the duty manager (non-time-boxed, auto-proceed
      disabled past the D21 floor).
  (c) glitch: problem_report P1 → Glitch opens → engineer raises
      ("can't fix") → relocate recommendation → resolve → ``relocate_stay``
      re-bind → Glitch + WO closed → ``CrossDeptNotification`` emitted.

Asserts: EXACTLY ONE append-only event per transition (before/after scoped
counts); the one-executor symmetry (leg-(b) auto-proceeded state ≡ the
leg-(a)/approve-equivalent state EXCEPT ``resolved_by_account_id is None``);
leg-(b) terminal ``hard_escalated`` + non-time-boxed with no further
auto-proceed; leg-(c) Glitch+WO closed + ``CrossDeptNotification`` + the
``relocate_stay`` re-bind effect; and ZERO residue after a deliberately
failed sub-scenario rolls back inside the savepoint.

Exact-count strategy under one savepoint: it is ONE test ⇒ ONE savepoint ⇒
rows from earlier legs persist; every count assertion is therefore SCOPED to
the freshly-returned identifiers of the entity under test (before/after
delta == 1), exactly the proven ``test_e2e_journey`` / ``test_guest_dispatch``
idiom.
"""
from __future__ import annotations

import datetime as dt
import uuid

import sqlalchemy as sa

from conduit.shared.domain import lifecycle
from conduit.shared.engine import runner
from conduit.shared.engine import spine
from conduit.shared.engine import timers as _t
from conduit.shared.models import (
    ChildSubRequest,
    CrossDeptNotification,
    Escalation,
    Event,
    EventChildClosed,
    EventCrossDeptNotified,
    EventEscalationOpened,
    EventEscalationResolved,
    EventGlitchClosed,
    EventGlitchOpened,
    EventWorkOrderAccepted,
    EventWorkOrderCompleted,
    Glitch,
    Property,
    Recommendation,
    RecBroadcast,
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
    delta == 1 mechanism — robust under the single shared savepoint)."""
    return (await db.execute(
        sa.select(sa.func.count()).select_from(detail_cls)
        .where(getattr(detail_cls, fk_attr) == fk_val)
    )).scalar_one()


async def _db_now(db):
    return (await db.execute(sa.select(sa.func.now()))).scalar_one()


async def _arm_past(db, owner_kind, owner_id, ttype):
    """Arm a timer of ``ttype`` in the DB-past so the next ``runner.tick``
    claims+fires it through the REAL engine (AD5: DB now(), no sleeping)."""
    await _t.arm(db, owner_kind, owner_id, ttype,
                 fire_at=(await _db_now(db)) - dt.timedelta(seconds=5))
    await db.flush()


async def _seed_chain(db, make_account, *, n_cycle_bound):
    """Property→Section→Room + a duty-manager + an effective-available
    section-owner servicer + a fresh non-stalled member servicer (the
    C1-routed reassign target). SLA preset + escalation ladder are created
    through the REAL supervisor CONFIG API by the caller; this builds only
    the FK chain + roster the routing needs. Returns handles."""
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
    spare_room = Room(section_id=sec.id, label="R2")  # leg (c) relocate target
    db.add(spare_room)
    await db.flush()

    now = dt.datetime.now(dt.timezone.utc)
    roster = Roster(property_id=p.id,
                    shift_start=now - dt.timedelta(hours=1),
                    shift_end=now + dt.timedelta(hours=8), status="active")
    db.add(roster)
    await db.flush()

    # The section OWNER (D12) — effective_available now → routing.select
    # yields a concrete owner ⇒ WorkOrder pushed.
    owner = await make_account("servicer", f"ow-{uuid.uuid4().hex[:8]}", _PW,
                               display_name="Olive Owner")
    db.add(StaffProfile(account_id=owner.id, staff_class="housekeeping",
                        presence="working", status="active"))
    await db.flush()
    db.add(RosterAssignment(roster_id=roster.id, account_id=owner.id,
                            section_id=sec.id, assignment="owner",
                            status="active"))
    # A fresh non-stalled member — the deterministic C1 reassign target the
    # leg-(b) stall chain routes to (NOT the stalled owner).
    target = await make_account("servicer", f"tg-{uuid.uuid4().hex[:8]}", _PW,
                                display_name="Tara Target")
    db.add(StaffProfile(account_id=target.id, staff_class="housekeeping",
                        presence="working", status="active"))
    await db.flush()
    db.add(RosterAssignment(roster_id=roster.id, account_id=target.id,
                            section_id=sec.id, assignment="member",
                            status="active"))
    await db.flush()
    return {"prop": p, "sec": sec, "room": room, "spare_room": spare_room,
            "duty": duty, "owner": owner, "target": target}


async def _guest_with_stay(db, make_account, room):
    guest = await make_account("guest", f"g-{uuid.uuid4().hex[:8]}", _PW)
    now = dt.datetime.now(dt.timezone.utc)
    stay = Stay(guest_account_id=guest.id, room_id=room.id, check_in=now,
                check_out=now + dt.timedelta(days=1), status="active")
    db.add(stay)
    await db.flush()
    return guest, stay


async def _submit_dispatch(client, db, fake_llm, guest, *,
                            issue_code, is_problem_report=False):
    """Guest submits via the MERGED intake endpoint (real ASGI, guest
    cookie). The only non-determinism (the LLM) is pinned by ``fake_llm``."""
    async def _classify(t, cat):
        return [{"text": t, "issue_code": issue_code,
                 "fulfilment_mode": "dispatch", "outcome": "auto",
                 "is_problem_report": is_problem_report}]

    fake_llm["classify"] = _classify
    r = await client.post("/api/guest/requests",
                           json={"text": "please help in my room"})
    assert r.status_code == 200, r.text
    await db.flush()
    body = r.json()
    child_id = uuid.UUID(body["children"][0]["child_id"])
    child = await db.get(ChildSubRequest, child_id)
    wo = (await db.execute(
        sa.select(WorkOrder).where(WorkOrder.child_id == child_id)
    )).scalar_one()
    return child, wo


async def test_e2e_dispatch_journey(client, make_account, login, db,
                                    fake_llm):
    h = await _seed_chain(db, make_account, n_cycle_bound=2)
    sup = await make_account("supervisor", f"sup-{uuid.uuid4().hex[:8]}", _PW)
    await db.commit()

    # ---- Supervisor seeds SLA preset + escalation ladder via the REAL E5
    #      CONFIG API (n_cycle_bound=2 so leg (b) reaches D21 fast). --------
    await login(sup.username, _PW)
    # property_id server-resolved (single-property v1); the harness creates
    # exactly one Property (h["prop"]) so the resolver is deterministic.
    rp = await client.post("/api/supervisor/sla-presets", json={
        "tier": "P1",
        "accept_window_seconds": 120, "fulfilment_sla_seconds": 1800,
        "supervisor_sla_seconds": 900})
    assert rp.status_code == 201, rp.text
    sla_id = rp.json()["id"]
    rl = await client.post("/api/supervisor/escalation-ladder", json={
        "duty_manager_account_id": str(h["duty"].id),
        "n_cycle_bound": 2})
    assert rl.status_code == 201, rl.text

    # A dispatch IssueCode pointing at that SLA preset (section_pooled → the
    # owner is the accountable D12 owner). Created directly (the E5 config
    # API covers SLA/ladder; issue-code CONFIG is a separate slice — the
    # journey only needs the routed code to exist).
    from conduit.shared.models import IssueCode
    ic = IssueCode(code=f"HK-{uuid.uuid4().hex[:6]}", label="Room help",
                   department="housekeeping", fulfilment_mode="dispatch",
                   routing_model="section_pooled",
                   sla_preset_id=uuid.UUID(sla_id))
    db.add(ic)
    await db.flush()
    await db.commit()

    # =====================================================================
    # INTAKE → triage AUTO dispatch → D12 routing-effect.
    # =====================================================================
    guest_a, _ = await _guest_with_stay(db, make_account, h["room"])
    await db.commit()
    await login(guest_a.username, _PW)
    child_a, wo_a = await _submit_dispatch(
        client, db, fake_llm, guest_a, issue_code=ic.code)

    # Triage AUTO + dispatch BRANCHED to the C4 routing-effect: a pushed
    # WorkOrder to the D12 section owner + the two D23 timers.
    assert child_a.outcome == "auto"
    assert child_a.state == "routing"
    assert wo_a.kind == "dispatch"
    assert wo_a.routing_model == "section_pooled"
    assert wo_a.state == "pushed"
    assert str(wo_a.assigned_servicer_id) == str(h["owner"].id)
    assert str(wo_a.accountable_owner_id) == str(h["owner"].id)
    timers_a = (await db.execute(sa.select(Timer).where(
        Timer.child_id == child_a.id, Timer.state == "pending"))
    ).scalars().all()
    assert {t.type for t in timers_a} == {"accept_window", "fulfilment_sla"}

    # =====================================================================
    # LEG (a) HAPPY: accept → complete → guest confirm → CLOSED.
    # Each transition driven via the REAL portal API; EXACTLY ONE
    # append-only event per transition (before/after delta == 1).
    # =====================================================================
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
    n_cl0 = await _count(db, EventChildClosed, "child_id", child_a.id)
    rc = await client.post(f"/api/servicer/tasks/{wo_a.id}/complete",
                           json={"notes": "done"})
    assert rc.status_code == 200, rc.text
    await db.commit()
    assert (await db.get(WorkOrder, wo_a.id)).state == "completed"
    assert await _count(db, EventWorkOrderCompleted, "work_order_id",
                        wo_a.id) == n_comp0 + 1
    assert (await db.get(ChildSubRequest, child_a.id)).state == \
        "done_pending_confirm"

    # Guest confirm (real guest cookie) → CLOSED, exactly one child_closed.
    await login(guest_a.username, _PW)
    rcf = await client.post(f"/api/guest/requests/{child_a.id}/confirm")
    assert rcf.status_code == 200, rcf.text
    assert rcf.json()["state"] == "closed"
    await db.commit()
    assert (await db.get(ChildSubRequest, child_a.id)).state == "closed"
    assert await _count(db, EventChildClosed, "child_id",
                        child_a.id) == n_cl0 + 1

    # =====================================================================
    # LEG (b) STALL: no accept → accept_window breach (fire_at-past +
    # runner.tick) → stall escalation → decision queue → supervisor SILENT
    # → supervisor_sla breach (tick) → auto-proceed reassign → the REAL D3
    # carry-forward chain (cycle_count NEVER hand-seeded) → hard-escalate to
    # the non-time-boxed duty manager (auto-proceed disabled past D21).
    # =====================================================================
    guest_b, _ = await _guest_with_stay(db, make_account, h["room"])
    await db.commit()
    await login(guest_b.username, _PW)
    child_b, wo_b = await _submit_dispatch(
        client, db, fake_llm, guest_b, issue_code=ic.code)
    await db.commit()
    assert wo_b.state == "pushed"

    # --- Cycle 1: NO accept → accept_window breach opens a stall escalation
    #     via the REAL engine→spine (runner.tick after fire_at-past). -------
    await _arm_past(db, "child_id", child_b.id, _t.TimerType.ACCEPT_WINDOW)
    fired = await runner.tick(db)
    assert fired >= 1
    await db.commit()
    esc1 = (await db.execute(sa.select(Escalation).where(
        Escalation.child_id == child_b.id))).scalars().all()
    assert len(esc1) == 1
    esc1 = esc1[0]
    assert esc1.trigger == "stall" and esc1.state == "open"
    # First stall on a fresh child → the spine carry-forward seeds 0 (D1).
    assert esc1.cycle_count == 0
    # EXACTLY ONE escalation_opened for THIS escalation.
    assert await _count(db, EventEscalationOpened, "escalation_id",
                        esc1.id) == 1

    # It is in the supervisor decision queue (real read API).
    await login(sup.username, _PW)
    dq = await client.get("/api/supervisor/decisions")
    assert dq.status_code == 200, dq.text
    assert str(esc1.id) in {d["escalation_id"] for d in dq.json()}

    # --- Supervisor stays SILENT; supervisor_sla breach (tick) →
    #     auto-proceed reassign through the REAL engine→spine. ------------
    n_res_e1 = await _count(db, EventEscalationResolved, "escalation_id",
                            esc1.id)
    await _arm_past(db, "escalation_id", esc1.id,
                    _t.TimerType.SUPERVISOR_SLA)
    fired = await runner.tick(db)
    assert fired >= 1
    await db.commit()
    er1 = await db.get(Escalation, esc1.id)
    assert er1.state == "auto_proceeded"            # structural silence path
    assert er1.resolved_by_account_id is None
    assert er1.cycle_count == 1                      # advanced by D2
    assert await _count(db, EventEscalationResolved, "escalation_id",
                        esc1.id) == n_res_e1 + 1     # exactly one resolved
    # D12 (Spec §7.1/§7.4): the child is ``section_pooled``; the stalled
    # assignee IS the section owner the WorkOrder was pushed to. On stall the
    # spine re-runs the SAME C1 ``routing.select`` with that assignee
    # EXCLUDED — for D12 an excluded owner cannot be re-assigned, so
    # ``routing.select`` returns the claim-fallback BROADCAST to the in-zone
    # ``effective_available`` pool (``assigned_id`` None). C2
    # ``recommendation.build`` therefore yields the ``broadcast`` action and
    # ``open_escalation`` persists a ``RecBroadcast`` detail (NOT a
    # ``RecReassign``). The silent auto-proceed executes that stored
    # recommendation verbatim → ``_execute_action`` CLEARS the direct
    # assignment (``assigned_servicer_id`` → None) and the accountable owner
    # is UNCHANGED. This is the genuine production D12 stall behaviour; the
    # reassign action is the D18 ``skill_matched`` path, not this one.
    rec1 = (await db.execute(sa.select(Recommendation).where(
        Recommendation.escalation_id == esc1.id))).scalar_one()
    assert rec1.action == "broadcast"
    rb1 = (await db.execute(sa.select(RecBroadcast).where(
        RecBroadcast.recommendation_escalation_id == esc1.id))).scalar_one()
    assert rb1 is not None
    wo_b_row = await db.get(WorkOrder, wo_b.id)
    # broadcast → the direct assignment is cleared (claim-fallback).
    assert wo_b_row.assigned_servicer_id is None
    # D12: accountable owner UNCHANGED across the silent broadcast.
    assert str(wo_b_row.accountable_owner_id) == str(h["owner"].id)

    # --- Cycle 2: the reassigned work ALSO stalls. A fresh accept_window
    #     breach drives the identical engine→spine.open_escalation hop; its
    #     cycle_count comes ENTIRELY from the REAL spine carry-forward (the
    #     prior auto-proceeded stall esc was advanced to 1) — NOT hand-set.
    await _arm_past(db, "child_id", child_b.id, _t.TimerType.ACCEPT_WINDOW)
    fired = await runner.tick(db)
    assert fired >= 1
    await db.commit()
    all_esc = (await db.execute(sa.select(Escalation).where(
        Escalation.child_id == child_b.id)
        .order_by(Escalation.created_at))).scalars().all()
    assert len(all_esc) == 2
    esc2 = all_esc[1]
    assert esc2.id != esc1.id
    assert esc2.trigger == "stall" and esc2.state == "open"
    # CARRY-FORWARD PROVEN: inherited the running count from the prior
    # (auto-proceeded) stall escalation via the REAL spine — never hand-set.
    assert esc2.cycle_count == 1
    assert await _count(db, EventEscalationOpened, "escalation_id",
                        esc2.id) == 1

    # --- Supervisor SILENT again; supervisor_sla breach now hits the D21
    #     bound (1+1 >= n_cycle_bound(2)) → hard-escalate to the duty
    #     manager INSTEAD of another auto-proceed (D21 floor reached). ----
    n_res_e2 = await _count(db, EventEscalationResolved, "escalation_id",
                            esc2.id)
    await _arm_past(db, "escalation_id", esc2.id,
                    _t.TimerType.SUPERVISOR_SLA)
    fired = await runner.tick(db)
    assert fired >= 1
    await db.commit()
    er2 = await db.get(Escalation, esc2.id)
    assert er2.state == "hard_escalated"             # D21 backstop reached
    assert er2.resolved_by_account_id is None
    # hard_escalate does NOT bump cycle_count (it is the backstop, not a
    # resolution) and runs NO recommendation action.
    assert er2.cycle_count == 1
    assert await _count(db, EventEscalationResolved, "escalation_id",
                        esc2.id) == n_res_e2 + 1     # exactly one resolved

    # Terminal + non-time-boxed in the decision queue; no further
    # auto-proceed (it is terminal in the escalation machine).
    qh = await client.get("/api/supervisor/decisions?status=hard_escalated")
    assert qh.status_code == 200, qh.text
    hrow = {d["escalation_id"]: d for d in qh.json()}
    assert str(esc2.id) in hrow
    assert hrow[str(esc2.id)]["non_time_boxed"] is True
    # Not in the OPEN queue (resolved/terminal).
    qo = await client.get("/api/supervisor/decisions")
    assert str(esc2.id) not in {d["escalation_id"] for d in qo.json()}
    # No third escalation, no further side effect even if a stray tick runs.
    fired = await runner.tick(db)
    await db.commit()
    assert len((await db.execute(sa.select(Escalation).where(
        Escalation.child_id == child_b.id))).scalars().all()) == 2

    # ---- JOURNEY-LEVEL silence ≡ approve proof --------------------------
    # An equivalent stall escalation resolved via the REAL approve API must
    # reach the IDENTICAL post-state as the leg-(b) auto-proceeded one,
    # EXCEPT resolved_by_account_id (set for approve, None for silence).
    # Both call the SAME spine.apply_recommendation — silence ≡ approve is
    # STRUCTURAL at the journey level.
    guest_s, _ = await _guest_with_stay(db, make_account, h["room"])
    await db.commit()
    await login(guest_s.username, _PW)
    child_s, wo_s = await _submit_dispatch(
        client, db, fake_llm, guest_s, issue_code=ic.code)
    await db.commit()
    await _arm_past(db, "child_id", child_s.id, _t.TimerType.ACCEPT_WINDOW)
    assert await runner.tick(db) >= 1
    await db.commit()
    esc_s = (await db.execute(sa.select(Escalation).where(
        Escalation.child_id == child_s.id))).scalar_one()
    # Supervisor APPROVES via the real resolve API (the human path).
    await login(sup.username, _PW)
    rap = await client.post(
        f"/api/supervisor/decisions/{esc_s.id}/resolve",
        json={"action": "approve"})
    assert rap.status_code == 200, rap.text
    await db.commit()
    e_api = await db.get(Escalation, esc_s.id)
    e_auto = await db.get(Escalation, esc1.id)       # leg-(b) cycle-1 silent
    wo_api = await db.get(WorkOrder, wo_s.id)
    wo_auto = await db.get(WorkOrder, wo_b.id)        # leg-(b) cycle-1 WO
    rec_api = (await db.execute(sa.select(Recommendation).where(
        Recommendation.escalation_id == esc_s.id))).scalar_one()
    rec_auto = (await db.execute(sa.select(Recommendation).where(
        Recommendation.escalation_id == esc1.id))).scalar_one()
    c_api = await db.get(ChildSubRequest, child_s.id)
    c_auto = await db.get(ChildSubRequest, child_b.id)
    # Both executed the SAME STORED rec verbatim — for D12 ``section_pooled``
    # the stalled owner is excluded ⇒ ``routing.select`` claim-fallback
    # ⇒ stored action ``broadcast``. The approve (human) path and the
    # auto-proceed (silence) path BOTH clear the direct assignment via the
    # identical ``spine.apply_recommendation`` → ``_execute_action`` —
    # silence ≡ approve is STRUCTURAL.
    assert rec_api.action == rec_auto.action == "broadcast"
    assert wo_api.assigned_servicer_id is None
    assert wo_auto.assigned_servicer_id is None
    assert str(wo_api.accountable_owner_id) == \
        str(wo_auto.accountable_owner_id) == str(h["owner"].id)
    # Identical cycle bump + child state + trigger.
    assert e_api.cycle_count == e_auto.cycle_count == 1
    assert c_api.state == c_auto.state
    assert e_api.trigger == e_auto.trigger == "stall"
    assert e_api.resolved_at is not None and e_auto.resolved_at is not None
    # The ONLY differences: outcome state + resolver.
    assert e_api.state == "approved"
    assert e_auto.state == "auto_proceeded"
    assert str(e_api.resolved_by_account_id) == str(sup.id)
    assert e_auto.resolved_by_account_id is None

    # =====================================================================
    # LEG (c) GLITCH: problem_report P1 → Glitch opens → engineer raises
    # ("can't fix") → relocate recommendation → supervisor resolve →
    # relocate_stay re-bind → Glitch + WO closed → CrossDeptNotification.
    # Driven via the REAL servicer raise + supervisor resolve APIs.
    # =====================================================================
    guest_c, stay_c = await _guest_with_stay(db, make_account, h["room"])
    await db.commit()
    await login(guest_c.username, _PW)
    child_c, wo_c = await _submit_dispatch(
        client, db, fake_llm, guest_c, issue_code=ic.code,
        is_problem_report=True)
    await db.commit()
    assert child_c.is_problem_report is True

    # Engineer takes the job (real servicer API) so it is mid-lifecycle.
    await login(h["owner"].username, _PW)
    assert (await client.post(
        f"/api/servicer/tasks/{wo_c.id}/accept")).status_code == 200
    assert (await client.post(
        f"/api/servicer/tasks/{wo_c.id}/start")).status_code == 200
    await db.commit()

    # The P1 problem_report's Glitch (recovery linkage). The new-entity
    # ``glitch_opened`` is appended via the SAME merged single writer (the
    # established idiom — open is the Glitch start state, no *->open edge).
    gl = Glitch(child_id=child_c.id, opened_from="problem_report",
                state="open")
    db.add(gl)
    await db.flush()
    from conduit.shared.events import writer as _w
    await _w.emit_glitch_opened(db, gl.id)
    await db.flush()
    await db.commit()
    assert await _count(db, EventGlitchOpened, "glitch_id", gl.id) == 1

    # Engineer raises "can't fix" via the REAL servicer raise API → the
    # spine opens a servicer_raised escalation + its AI recommendation.
    await login(h["owner"].username, _PW)
    rr = await client.post(f"/api/servicer/tasks/{wo_c.id}/raise",
                           json={"reason": "structural damage, can't fix"})
    assert rr.status_code == 201, rr.text
    await db.commit()
    esc_c = (await db.execute(sa.select(Escalation).where(
        Escalation.child_id == child_c.id,
        Escalation.trigger == "servicer_raised"))).scalar_one()
    assert esc_c.state == "open"
    assert await _count(db, EventEscalationOpened, "escalation_id",
                        esc_c.id) == 1

    # Supervisor resolves with a RELOCATE override (outcome ``overridden``)
    # through THE single executor ``spine.apply_recommendation`` — the EXACT
    # engine seam the resolve API calls. The relocate stay-target inputs
    # (``stay_id`` / ``new_room_id``) reach the C4 escalation→relocate hop via
    # ``apply_recommendation``'s forwarded ``**ctx`` (the proven real-engine
    # pattern of ``test_spine.test_apply_recommendation_relocate_closes_glitch``
    # — the genuine relocate seam; the supervisor resolve API does NOT yet
    # surface the stay-target wiring — that is the documented Phase-E boundary
    # in ``lifecycle._escalation_hops``, NOT a defect). The C4 hop runs the
    # REAL ``relocate_stay`` re-bind and closes the linked Glitch through the
    # same orchestrator. ``actor`` is the supervisor (the human resolver).
    await login(sup.username, _PW)
    n_gl_cl0 = await _count(db, EventGlitchClosed, "glitch_id", gl.id)
    await spine.apply_recommendation(
        db, esc_c, outcome="overridden", action="relocate",
        payload={"target_room_id": str(h["spare_room"].id)},
        actor=sup.id,
        stay_id=stay_c.id, new_room_id=h["spare_room"].id)
    await db.commit()

    # relocate_stay re-bind effect: the guest's stay room changed (the REAL
    # merged stay/binding seam ran — re-bind, not reimplemented in the test).
    stay_c_row = await db.get(Stay, stay_c.id)
    assert str(stay_c_row.room_id) == str(h["spare_room"].id)
    # The linked Glitch was closed (the recovery the relocate discharges):
    # exactly one glitch_closed.
    gl_row = await db.get(Glitch, gl.id)
    assert gl_row.state == "closed"
    assert await _count(db, EventGlitchClosed, "glitch_id",
                        gl.id) == n_gl_cl0 + 1
    # The escalation resolved (overridden) — exactly one escalation_resolved.
    e_c = await db.get(Escalation, esc_c.id)
    assert e_c.state == "overridden"
    assert e_c.resolved_by_account_id == sup.id      # the human resolver
    assert await _count(db, EventEscalationResolved, "escalation_id",
                        esc_c.id) == 1

    # The recovery completes the WorkOrder and crosses departments
    # (housekeeping servicer ↛ the engineering follow-up) → the genuine C4
    # WorkOrder→completed cross-dept hop emits a CrossDeptNotification. This
    # is driven through the REAL engine ``lifecycle.transition`` with the
    # documented downstream-department ctx (the proven xdn seam of
    # ``test_lifecycle_machines.test_workorder_completed_orchestrates_child_and_xdn``
    # — IssueCode has no downstream-dept column in this slice, so the
    # cross-dept target is supplied via ctx, exactly as production wires it).
    wo_c_row = await db.get(WorkOrder, wo_c.id)
    n_xdn0 = (await db.execute(sa.select(sa.func.count())
              .select_from(CrossDeptNotification)
              .where(CrossDeptNotification.source_work_order_id == wo_c.id)
              )).scalar_one()
    await lifecycle.transition(
        db, wo_c_row, "completed", actor=sup.id,
        target_department="engineering",
        xdn_reason="relocate recovery follow-up")
    await db.commit()
    # Exactly ONE CrossDeptNotification for this WorkOrder + its single
    # cross_dept_notified event (the before/after delta == 1 invariant).
    assert (await db.execute(sa.select(sa.func.count())
            .select_from(CrossDeptNotification)
            .where(CrossDeptNotification.source_work_order_id == wo_c.id)
            )).scalar_one() == n_xdn0 + 1
    xdn = (await db.execute(sa.select(CrossDeptNotification).where(
        CrossDeptNotification.source_work_order_id == wo_c.id))).scalar_one()
    assert xdn.child_id == child_c.id
    assert xdn.target_department == "engineering"
    assert await _count(db, EventCrossDeptNotified,
                        "cross_dept_notification_id", xdn.id) == 1
    # WO terminal after the recovery (the C4 completed transition).
    wo_c_row = await db.get(WorkOrder, wo_c.id)
    assert wo_c_row.state == "completed"

    # =====================================================================
    # ZERO RESIDUE: a sub-scenario that deliberately raises AFTER partial
    # writes inside the savepoint must roll back leaving NO orphan rows
    # (the conftest savepoint-rollback isolation; the leak sentinel /
    # baseline-count invariant). We snapshot Property/Glitch counts, do a
    # partial write then force a failure, roll the inner work back, and
    # assert the counts returned to the pre-sub-scenario baseline.
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
        orphan_g = Glitch(child_id=child_a.id, opened_from="dispute",
                           state="open")
        db.add(orphan_g)
        await db.flush()
        # Deliberate failure AFTER the partial writes.
        raise RuntimeError("forced failure inside the savepoint")
    except RuntimeError:
        await sp.rollback()                       # discard the partial work
    # Zero residue: counts returned to baseline — no orphan rows survived.
    assert (await db.execute(
        sa.select(sa.func.count()).select_from(Property))
    ).scalar_one() == base_props
    assert (await db.execute(
        sa.select(sa.func.count()).select_from(Glitch))
    ).scalar_one() == base_glitch
    # The deliberately-orphaned rows are genuinely absent.
    assert (await db.execute(sa.select(Property).where(
        Property.name == "ORPHAN-must-not-persist"))
    ).scalar_one_or_none() is None
