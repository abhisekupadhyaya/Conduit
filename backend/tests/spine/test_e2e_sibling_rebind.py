"""Spec §9.2 / §11 — the cross-slice sibling-rebind integration proof.

This is the program's reason-to-exist test (relocation-subflow §9.2 "Flow
(walkable, cross-slice)" + §11 "Cross-slice e2e"; multi-intent-fanout §9.2):
a Slice-7 fan of ``{AC-problem child, towel child}`` from ONE guest message
walks the REAL portal APIs + the REAL engine all the way through a
relocation and proves the live towel sibling FOLLOWS the re-bound stay with
NO per-sibling write.

Walk (every transition driven via the REAL ASGI client + the REAL engine —
NOTHING re-implemented):

  * ONE utterance → ``decompose`` (``fake_decompose`` double) splits TWO
    needs → per-child ``classify`` (``fake_llm``) fans into TWO children
    sharing the ONE parent Request/Stay:
      - Child AC — an ``ENG-*`` problem-report → C4 routing (pushed WO) →
        engineer accept/start → Glitch opens → engineer raises "can't fix"
        (real servicer raise API) → the spine COMPUTES + PERSISTS the
        relocate target room (B4 §7.2 — the LLM never in the path).
      - Child TOWEL — a plain ``HK-*`` dispatch → C4 routing (pushed WO);
        it stays LIVE (never accepted/closed) throughout.
  * Supervisor resolves the AC relocate through the REAL
    ``POST /supervisor/decisions/{id}/resolve`` — covered TWICE on two
    independent equivalent seeds:
      (A) ``approve``  → re-bind to the COMPUTED+PERSISTED room,
      (B) silent auto-proceed → ``_arm_past`` supervisor_sla +
          ``runner.tick`` (the REAL engine) on the PERSISTED room.
    Per spec §7.4 the auto-proceed end-state ≡ approve EXCEPT
    ``resolved_by_account_id`` (set for approve, None for silence).
  * The REAL ``relocate_stay`` re-binds the shared Stay → the AC Glitch
    closes → a ``relocation_move`` child + ``WorkOrder kind='relocation_move'``
    spawn (B5 §7.3 — same ``request_id``, ``predecessor_child_id`` = the AC
    child) routed section_pooled to the FRONT-OFFICE servicer.
  * THE INTEGRATION PROOF: the still-live TOWEL sibling's ambient room
    re-resolves to the NEW room with NO per-sibling write —
    ``GET /api/guest/requests`` shows ``relocated_to`` = the NEW room label
    on the live towel card (B6 §7.4 / D22), and the towel child was NEVER
    blocked/advanced by the AC child's escalation+recovery (sibling
    independence — §9.2 fan-out guarantee).

Asserted invariants (the proven idioms — nothing invented):
  * ``split is True`` + EXACTLY two children sharing the one Request.
  * EXACTLY ONE append-only event per transition — the scoped before/after
    ``_count(db, EventX, fk, id)`` delta == 1 idiom from
    ``test_e2e_dispatch.py`` / ``test_e2e_fanout.py``.
  * The towel sibling re-resolves with NO per-sibling write (it is never
    transitioned by the AC recovery; its card just reads the re-bound room).
  * ZERO residue on a deliberately-failed sub-leg: an inner SAVEPOINT
    partial write + forced failure rolls back leaving the post-relocation
    end-state and the global row counts untouched (savepoint isolation).

Built ENTIRELY from the proven helpers/idioms in
``tests/spine/test_e2e_dispatch.py`` / ``tests/spine/test_e2e_fanout.py``
(real per-test ``client``, real per-role ``login`` cookie chain, real
engine, savepoint-isolated ``db``, scoped ``_count`` deltas, ``_arm_past`` +
``runner.tick``). Nothing is invented.
"""
from __future__ import annotations

import datetime as dt
import uuid

import sqlalchemy as sa

from conduit.shared.engine import runner
from conduit.shared.engine import timers as _t
from conduit.shared.models import (
    ChildSubRequest,
    Escalation,
    EventChildRouted,
    EventEscalationOpened,
    EventEscalationResolved,
    EventGlitchClosed,
    EventGlitchOpened,
    EventGuestRelocated,
    EventRequestCreated,
    EventWorkOrderCreated,
    Glitch,
    IssueCode,
    Property,
    RecRelocate,
    Room,
    Roster,
    RosterAssignment,
    Section,
    StaffProfile,
    Stay,
    WorkOrder,
)

_PW = "pw-123456"  # conftest default in make_account / login


async def _count(db, detail_cls, fk_attr, fk_val) -> int:
    """Scoped append-only event count for one entity (the before/after
    delta == 1 mechanism — robust under the single shared savepoint;
    verbatim from test_e2e_dispatch.py / test_e2e_fanout.py)."""
    return (await db.execute(
        sa.select(sa.func.count()).select_from(detail_cls)
        .where(getattr(detail_cls, fk_attr) == fk_val)
    )).scalar_one()


async def _db_now(db):
    return (await db.execute(sa.select(sa.func.now()))).scalar_one()


async def _arm_past(db, owner_kind, owner_id, ttype):
    """Arm a timer of ``ttype`` in the DB-past so the next ``runner.tick``
    claims+fires it through the REAL engine (AD5: DB now(), no sleeping —
    verbatim from test_e2e_dispatch.py)."""
    await _t.arm(db, owner_kind, owner_id, ttype,
                 fire_at=(await _db_now(db)) - dt.timedelta(seconds=5))
    await db.flush()


async def _seed_chain(db, make_account):
    """Property→Section→Room + a SEPARATE front-office Section whose OWNER is
    a front-office servicer (spec §9.1 "Servicer B (runner/front-office)" —
    the spawned ``relocation_move`` WO routes section_pooled into the
    relocated room's section so it surfaces on the front-office queue) + the
    engineering owner that takes the AC problem-report + an HK owner that the
    towel WO routes to. SLA preset + escalation ladder are created through the
    REAL supervisor CONFIG API by the caller; FO-GUEST-MOVE is seeded here
    (the spine-package leakage-reset truncates the migration seed — the exact
    test_e2e_dispatch.py::_seed_chain idiom). Returns handles."""
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
    # The relocate targets live in a SEPARATE front-office section whose
    # OWNER is a front-office servicer. ``spare_room`` is the deterministic
    # recommended pick (room_selection orders by label then id); disjoint
    # labels make the ordering unambiguous.
    fo_sec = Section(property_id=p.id, label="FO")
    db.add(fo_sec)
    await db.flush()
    spare_room = Room(section_id=fo_sec.id, label="FR1")
    db.add(spare_room)
    await db.flush()
    spare_room2 = Room(section_id=fo_sec.id, label="FR2")
    db.add(spare_room2)
    await db.flush()

    now = dt.datetime.now(dt.timezone.utc)
    roster = Roster(property_id=p.id,
                    shift_start=now - dt.timedelta(hours=1),
                    shift_end=now + dt.timedelta(hours=8), status="active")
    db.add(roster)
    await db.flush()

    # The section OWNER (D12) — effective_available now → routing.select
    # yields a concrete owner ⇒ both child WorkOrders push to them.
    owner = await make_account("servicer", f"ow-{uuid.uuid4().hex[:8]}", _PW,
                               display_name="Olive Owner")
    db.add(StaffProfile(account_id=owner.id, staff_class="housekeeping",
                        presence="working", status="active"))
    await db.flush()
    db.add(RosterAssignment(roster_id=roster.id, account_id=owner.id,
                            section_id=sec.id, assignment="owner",
                            status="active"))
    await db.flush()
    # The FRONT-OFFICE servicer who OWNS ``fo_sec`` — section_pooled routing
    # of the spawned ``relocation_move`` WO assigns it here, so the move task
    # is a PUSHED card on this servicer's existing queue.
    fo = await make_account("servicer", f"fo-{uuid.uuid4().hex[:8]}", _PW,
                            display_name="Felix Frontdesk")
    db.add(StaffProfile(account_id=fo.id, staff_class="runner",
                        presence="working", status="active"))
    await db.flush()
    db.add(RosterAssignment(roster_id=roster.id, account_id=fo.id,
                            section_id=fo_sec.id, assignment="owner",
                            status="active"))
    await db.flush()

    # The system FO-GUEST-MOVE issue code (B1 seeds it via migration 0007;
    # the spine-package leakage-reset TRUNCATEs all data once before the
    # first spine session, clearing that seed row — so seed it here, exactly
    # the established test_e2e_dispatch.py / test_spine idiom; the journey
    # only needs the routed code to exist). Idempotent insert-missing.
    fo_ic = (await db.execute(sa.select(IssueCode).where(
        sa.func.lower(IssueCode.code) == "fo-guest-move"))).scalars().first()
    if fo_ic is None:
        fo_ic = IssueCode(code="FO-GUEST-MOVE", label="Guest move",
                          department="front_office",
                          fulfilment_mode="dispatch",
                          routing_model="section_pooled",
                          intent_kind="service",
                          is_reservation_mutation=False, origin="system",
                          status="active")
        db.add(fo_ic)
        await db.flush()
    return {"prop": p, "sec": sec, "room": room, "fo_sec": fo_sec,
            "spare_room": spare_room, "spare_room2": spare_room2,
            "fo": fo, "fo_ic": fo_ic, "duty": duty, "owner": owner}


async def _guest_with_stay(db, make_account, room):
    guest = await make_account("guest", f"g-{uuid.uuid4().hex[:8]}", _PW)
    now = dt.datetime.now(dt.timezone.utc)
    stay = Stay(guest_account_id=guest.id, room_id=room.id, check_in=now,
                check_out=now + dt.timedelta(days=1), status="active")
    db.add(stay)
    await db.flush()
    return guest, stay


async def _fan_two(client, db, fake_llm, fake_decompose, *, hk_code,
                   eng_code):
    """ONE utterance → decompose TWO needs → the REAL fan via the REAL
    POST /api/guest/requests. Returns (request_id, towel_child_id,
    ac_child_id, ac_wo, towel_wo)."""
    fake_decompose["texts"] = [
        "please send extra towels",
        "the AC is broken",
    ]

    async def fclassify(t, cat):
        if "towel" in t:
            return [{"text": t, "issue_code": hk_code,
                     "fulfilment_mode": "dispatch", "outcome": "auto",
                     "is_problem_report": False}]
        return [{"text": t, "issue_code": eng_code,
                 "fulfilment_mode": "dispatch", "outcome": "auto",
                 "is_problem_report": True}]

    fake_llm["classify"] = fclassify
    r = await client.post("/api/guest/requests",
                          json={"text": "towels, and the AC is broken"})
    assert r.status_code == 200, r.text
    await db.flush()
    body = r.json()
    assert body["split"] is True
    assert len(body["children"]) == 2
    req_id = uuid.UUID(body["request_id"])
    # EXACTLY ONE request_created for the single parent Request (scoped).
    assert await _count(db, EventRequestCreated, "request_id", req_id) == 1

    by_code = {c["issue_code"]: c for c in body["children"]}
    assert set(by_code) == {hk_code, eng_code}
    towel_id = uuid.UUID(by_code[hk_code]["child_id"])
    ac_id = uuid.UUID(by_code[eng_code]["child_id"])
    assert towel_id != ac_id
    for cid in (towel_id, ac_id):
        assert (await db.get(ChildSubRequest, cid)).request_id == req_id
    ac_wo = (await db.execute(sa.select(WorkOrder).where(
        WorkOrder.child_id == ac_id))).scalar_one()
    towel_wo = (await db.execute(sa.select(WorkOrder).where(
        WorkOrder.child_id == towel_id))).scalar_one()
    assert ac_wo.state == "pushed" and towel_wo.state == "pushed"
    return req_id, towel_id, ac_id, ac_wo, towel_wo


async def _raise_ac_relocate(client, db, login, h, ac_wo, ac_id):
    """Engineer accept/start the AC WO → open its Glitch (the merged single
    writer idiom) → engineer raises "can't fix" via the REAL servicer raise
    API → the spine opens a servicer_raised escalation and COMPUTES+PERSISTS
    the relocate target on RecRelocate.target_room_id (B4 §7.2). Returns
    (glitch, escalation, persisted_target_room_id)."""
    await login(h["owner"].username, _PW)
    assert (await client.post(
        f"/api/servicer/tasks/{ac_wo.id}/accept")).status_code == 200
    assert (await client.post(
        f"/api/servicer/tasks/{ac_wo.id}/start")).status_code == 200
    await db.commit()
    gl = Glitch(child_id=ac_id, opened_from="problem_report", state="open")
    db.add(gl)
    await db.flush()
    from conduit.shared.events import writer as _w
    await _w.emit_glitch_opened(db, gl.id)
    await db.flush()
    await db.commit()
    assert await _count(db, EventGlitchOpened, "glitch_id", gl.id) == 1

    await login(h["owner"].username, _PW)
    rr = await client.post(f"/api/servicer/tasks/{ac_wo.id}/raise",
                           json={"reason": "compressor dead, can't fix"})
    assert rr.status_code == 201, rr.text
    await db.commit()
    esc = (await db.execute(sa.select(Escalation).where(
        Escalation.child_id == ac_id,
        Escalation.trigger == "servicer_raised"))).scalar_one()
    assert esc.state == "open"
    assert await _count(db, EventEscalationOpened, "escalation_id",
                        esc.id) == 1
    # B4 §7.2: the relocate target is COMPUTED + PERSISTED at build (the
    # deterministic available pick — selection never re-runs).
    rr_row = (await db.execute(sa.select(RecRelocate).where(
        RecRelocate.recommendation_escalation_id == esc.id))).scalar_one()
    assert rr_row.target_room_id is not None
    return gl, esc, rr_row.target_room_id


async def _assert_move_task(db, client, login, h, ac_child_id,
                            ac_request_id):
    """B5 §7.3: EXACTLY ONE ``relocation_move`` move child (same request_id,
    ``predecessor_child_id`` = the AC child) + EXACTLY ONE
    ``WorkOrder kind='relocation_move'`` acceptable by the front-office
    servicer through the REAL servicer-tasks accept path. Exactly one
    append-only event per spawn transition."""
    moves = (await db.execute(sa.select(ChildSubRequest).where(
        ChildSubRequest.predecessor_child_id == ac_child_id)
    )).scalars().all()
    assert len(moves) == 1, "exactly one relocation_move child"
    mv = moves[0]
    assert mv.request_id == ac_request_id        # same Request (5a)
    assert mv.id != ac_child_id
    assert mv.fulfilment_mode == "dispatch"
    assert await _count(db, EventChildRouted, "child_id", mv.id) == 1
    mv_wos = (await db.execute(sa.select(WorkOrder).where(
        WorkOrder.child_id == mv.id))).scalars().all()
    assert len(mv_wos) == 1
    mv_wo = mv_wos[0]
    assert mv_wo.kind == "relocation_move"
    assert await _count(db, EventWorkOrderCreated, "work_order_id",
                        mv_wo.id) == 1
    # Acceptable by the front-office servicer via the REAL accept path.
    await login(h["fo"].username, _PW)
    tl = await client.get("/api/servicer/tasks")
    assert tl.status_code == 200, tl.text
    assert str(mv_wo.id) in {str(t["work_order_id"]) for t in tl.json()}
    racc = await client.post(f"/api/servicer/tasks/{mv_wo.id}/accept")
    assert racc.status_code == 200, racc.text
    await db.commit()
    assert (await db.get(WorkOrder, mv_wo.id)).state == "accepted"
    return mv, mv_wo


async def _towel_card(client, towel_id):
    """The live towel sibling's card off the REAL GET /api/guest/requests."""
    rq = await client.get("/api/guest/requests")
    assert rq.status_code == 200, rq.text
    by_child = {c["child_id"]: c for c in rq.json()}
    assert str(towel_id) in by_child, "towel card must be visible (live)"
    return by_child[str(towel_id)]


async def test_e2e_sibling_rebind_cross_slice(client, make_account, login,
                                              db, fake_llm, fake_decompose):
    h = await _seed_chain(db, make_account)
    sup = await make_account("supervisor", f"sup-{uuid.uuid4().hex[:8]}", _PW)
    await db.commit()

    # ---- Supervisor seeds SLA preset + escalation ladder via the REAL E5
    #      CONFIG API (the proven test_e2e_dispatch.py idiom). --------------
    await login(sup.username, _PW)
    rp = await client.post("/api/supervisor/sla-presets", json={
        "tier": "P1",
        "accept_window_seconds": 120, "fulfilment_sla_seconds": 1800,
        "supervisor_sla_seconds": 900})
    assert rp.status_code == 201, rp.text
    sla_id = rp.json()["id"]
    rl = await client.post("/api/supervisor/escalation-ladder", json={
        "duty_manager_account_id": str(h["duty"].id),
        "n_cycle_bound": 3})
    assert rl.status_code == 201, rl.text

    # Two dispatch IssueCodes (one HK towel, one ENG problem-report AC) —
    # both section_pooled at the one seeded owner. Created directly
    # (issue-code CONFIG is a separate slice; the journey only needs the
    # routed codes to exist — the exact test_e2e_dispatch.py idiom).
    hk_code = f"HK-TOWEL-{uuid.uuid4().hex[:6]}"
    eng_code = f"ENG-AC-{uuid.uuid4().hex[:6]}"
    db.add(IssueCode(code=hk_code, label="Extra towels",
                     department="housekeeping", fulfilment_mode="dispatch",
                     routing_model="section_pooled",
                     sla_preset_id=uuid.UUID(sla_id)))
    db.add(IssueCode(code=eng_code, label="AC not working",
                     department="engineering", fulfilment_mode="dispatch",
                     routing_model="section_pooled",
                     intent_kind="problem_report",
                     sla_preset_id=uuid.UUID(sla_id)))
    await db.flush()
    await db.commit()

    # =====================================================================
    # SCENARIO A — supervisor APPROVE. ONE utterance → {towel, AC} fan →
    # AC Glitch + ENG raise → spine computes+persists → approve → real
    # relocate_stay re-binds the SHARED stay → AC Glitch closed →
    # relocation_move spawned → the LIVE towel sibling re-resolves.
    # =====================================================================
    guest_a, stay_a = await _guest_with_stay(db, make_account, h["room"])
    await db.commit()
    await login(guest_a.username, _PW)
    req_a, towel_a, ac_a, ac_wo_a, towel_wo_a = await _fan_two(
        client, db, fake_llm, fake_decompose,
        hk_code=hk_code, eng_code=eng_code)
    await db.commit()

    # Sibling independence (pre): the towel card is LIVE and NOT yet
    # relocated (no guest_relocated event exists for this stay).
    await login(guest_a.username, _PW)
    pre = await _towel_card(client, towel_a)
    assert pre["relocated_to"] is None
    assert await _count(db, EventGuestRelocated, "stay_id", stay_a.id) == 0

    gl_a, esc_a, persisted_a = await _raise_ac_relocate(
        client, db, login, h, ac_wo_a, ac_a)

    # The towel sibling is UNTOUCHED by the AC child's escalation (sibling
    # independence — its WO is still pushed, no escalation on it).
    assert (await db.get(WorkOrder, towel_wo_a.id)).state == "pushed"
    assert (await db.execute(sa.select(sa.func.count())
            .select_from(Escalation)
            .where(Escalation.child_id == towel_a))).scalar_one() == 0

    # Supervisor APPROVE via the REAL resolve route → the single executor
    # re-binds the SHARED stay to the COMPUTED+PERSISTED room.
    await login(sup.username, _PW)
    n_gl_cl0 = await _count(db, EventGlitchClosed, "glitch_id", gl_a.id)
    rok = await client.post(
        f"/api/supervisor/decisions/{esc_a.id}/resolve",
        json={"action": "approve"})
    assert rok.status_code == 200, rok.text
    await db.commit()
    # Real relocate_stay re-bind on the SHARED stay (B4): the persisted room.
    stay_a_row = await db.get(Stay, stay_a.id)
    assert str(stay_a_row.room_id) == str(persisted_a)
    # The AC Glitch closed (the recovery the relocate discharges): exactly
    # one glitch_closed (append-only delta == 1).
    assert (await db.get(Glitch, gl_a.id)).state == "closed"
    assert await _count(db, EventGlitchClosed, "glitch_id",
                        gl_a.id) == n_gl_cl0 + 1
    e_a = await db.get(Escalation, esc_a.id)
    assert e_a.state == "approved"
    assert str(e_a.resolved_by_account_id) == str(sup.id)
    assert await _count(db, EventEscalationResolved, "escalation_id",
                        esc_a.id) == 1
    # EXACTLY ONE guest_relocated event for the shared stay (append-only).
    assert await _count(db, EventGuestRelocated, "stay_id", stay_a.id) == 1
    # The relocation_move child + WO spawned (B5) on the front-office queue.
    mv_a, mv_wo_a = await _assert_move_task(db, client, login, h, ac_a,
                                            req_a)

    # ---- THE INTEGRATION PROOF ------------------------------------------
    # The still-live TOWEL sibling re-resolves its ambient room to the NEW
    # room with NO per-sibling write: its card's ``relocated_to`` == the new
    # room label (B6 §7.4 / D22). The towel child was NEVER transitioned by
    # the AC recovery (its state/WO are unchanged — sibling independence).
    new_room_label = (await db.get(Room, persisted_a)).label
    await login(guest_a.username, _PW)
    post = await _towel_card(client, towel_a)
    assert post["relocated_to"] == new_room_label
    assert post["issue_label"] == "Extra towels"   # still the towel card
    # NO per-sibling write: the towel child row + its WO are byte-unchanged
    # by the AC recovery (it merely READS the re-bound stay's room).
    towel_row = await db.get(ChildSubRequest, towel_a)
    assert towel_row.state == "routing"            # never advanced
    assert towel_row.predecessor_child_id is None  # not the move child
    assert (await db.get(WorkOrder, towel_wo_a.id)).state == "pushed"
    # The towel child has ZERO escalations and ZERO child_routed beyond its
    # own single intake routing (it was never re-routed by the recovery).
    assert (await db.execute(sa.select(sa.func.count())
            .select_from(Escalation)
            .where(Escalation.child_id == towel_a))).scalar_one() == 0
    assert await _count(db, EventChildRouted, "child_id", towel_a) == 1

    # =====================================================================
    # SCENARIO B — a fresh INDEPENDENT seed; identical fan + raise but the
    # supervisor stays SILENT: ``_arm_past`` supervisor_sla + ``runner.tick``
    # auto-proceeds through the REAL engine on the PERSISTED room. Spec §7.4:
    # the end-state ≡ Scenario A's approve EXCEPT resolved_by_account_id.
    # =====================================================================
    guest_b, stay_b = await _guest_with_stay(db, make_account, h["room"])
    await db.commit()
    await login(guest_b.username, _PW)
    req_b, towel_b, ac_b, ac_wo_b, towel_wo_b = await _fan_two(
        client, db, fake_llm, fake_decompose,
        hk_code=hk_code, eng_code=eng_code)
    await db.commit()
    await login(guest_b.username, _PW)
    assert (await _towel_card(client, towel_b))["relocated_to"] is None

    gl_b, esc_b, persisted_b = await _raise_ac_relocate(
        client, db, login, h, ac_wo_b, ac_b)
    n_gl_cl0_b = await _count(db, EventGlitchClosed, "glitch_id", gl_b.id)
    n_res_b = await _count(db, EventEscalationResolved, "escalation_id",
                           esc_b.id)

    # Supervisor SILENT → supervisor_sla breach (fire_at-past) +
    # runner.tick → auto-proceed on the PERSISTED room (selection never
    # re-runs — B4 §7.2). NO ctx supplied; the REAL engine drives it.
    await _arm_past(db, "escalation_id", esc_b.id,
                    _t.TimerType.SUPERVISOR_SLA)
    assert await runner.tick(db) >= 1
    await db.commit()
    e_b = await db.get(Escalation, esc_b.id)
    assert e_b.state == "auto_proceeded"           # structural silence path
    assert e_b.resolved_by_account_id is None      # silence ≡ approve
    stay_b_row = await db.get(Stay, stay_b.id)
    assert str(stay_b_row.room_id) == str(persisted_b)  # PERSISTED room
    assert (await db.get(Glitch, gl_b.id)).state == "closed"
    assert await _count(db, EventGlitchClosed, "glitch_id",
                        gl_b.id) == n_gl_cl0_b + 1
    assert await _count(db, EventEscalationResolved, "escalation_id",
                        esc_b.id) == n_res_b + 1   # exactly one resolved
    assert await _count(db, EventGuestRelocated, "stay_id", stay_b.id) == 1
    await _assert_move_task(db, client, login, h, ac_b, req_b)

    # The live towel sibling on the SILENT path ALSO re-resolves to the new
    # room with no per-sibling write — the cross-slice proof holds for the
    # auto-proceed path identically (the integration proof, silent variant).
    new_room_label_b = (await db.get(Room, persisted_b)).label
    await login(guest_b.username, _PW)
    post_b = await _towel_card(client, towel_b)
    assert post_b["relocated_to"] == new_room_label_b
    assert (await db.get(ChildSubRequest, towel_b)).state == "routing"
    assert (await db.get(WorkOrder, towel_wo_b.id)).state == "pushed"

    # spec §7.4 one-executor symmetry: auto-proceed (B) ≡ approve (A) in
    # EVERY structural field except the resolver + the outcome label.
    assert e_a.trigger == e_b.trigger == "servicer_raised"
    assert e_a.resolved_at is not None and e_b.resolved_at is not None
    assert e_a.cycle_count == e_b.cycle_count
    assert e_a.state == "approved" and e_b.state == "auto_proceeded"
    assert str(e_a.resolved_by_account_id) == str(sup.id)
    assert e_b.resolved_by_account_id is None

    # =====================================================================
    # ZERO RESIDUE on a deliberately-failed sub-leg: an inner SAVEPOINT
    # partial write + forced failure rolls back leaving the post-relocation
    # end-state AND the global row counts untouched (savepoint isolation —
    # one failed sub-leg cannot corrupt the relocation it follows).
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
        orphan_g = Glitch(child_id=towel_a, opened_from="dispute",
                           state="open")
        db.add(orphan_g)
        await db.flush()
        raise RuntimeError("forced failure inside the savepoint")
    except RuntimeError:
        await sp.rollback()                       # discard the partial work
    # Zero residue: global counts returned to baseline — no orphans survived.
    assert (await db.execute(
        sa.select(sa.func.count()).select_from(Property))
    ).scalar_one() == base_props
    assert (await db.execute(
        sa.select(sa.func.count()).select_from(Glitch))
    ).scalar_one() == base_glitch
    assert (await db.execute(sa.select(Property).where(
        Property.name == "ORPHAN-must-not-persist"))
    ).scalar_one_or_none() is None
    # The post-relocation end-state SURVIVED the failed sub-leg intact —
    # the re-bound stays + closed Glitches + the live towel siblings'
    # re-resolved cards are structural, not corrupted by the rollback.
    assert str((await db.get(Stay, stay_a.id)).room_id) == str(persisted_a)
    assert str((await db.get(Stay, stay_b.id)).room_id) == str(persisted_b)
    assert (await db.get(Glitch, gl_a.id)).state == "closed"
    assert (await db.get(Glitch, gl_b.id)).state == "closed"
    await login(guest_a.username, _PW)
    assert (await _towel_card(client, towel_a))["relocated_to"] == \
        (await db.get(Room, persisted_a)).label
