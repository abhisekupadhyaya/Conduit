"""Task E3 — Supervisor decision queue + ``/resolve`` (Spec §8 / §7.4 /
§9.2 + the decision-ledger surface).

ONE full-ASGI scripted test driven over the merged per-test ``client``
with a real per-role cookie chain (``login`` swaps the single active
session cookie — the proven idiom in ``test_servicer_tasks`` /
``test_staffing_api`` / ``test_guest_dispatch``).

Open escalations are seeded through the spine ``open_escalation`` (the
Phase-D seed idiom) so the recommendation + its ``rec_*`` detail + the
``supervisor_sla`` Timer are produced by the spine, never re-implemented.

The surface is exercised end to end with the full status matrix
(200 / 401 / 403 / 409 / 422 / 405) and — the slice's reason to exist —
the STRUCTURAL silence ≡ approve proof: one escalation resolved via the
API (`approve`) and an equivalent one driven by the engine auto-proceed
path (``runner.tick`` after arming its ``supervisor_sla`` timer in the
past) end up IDENTICAL except ``resolved_by_account_id`` (set for the
API-approved one, ``None`` for the auto-proceeded one). Both paths call
the SAME ``spine.apply_recommendation`` — the API just maps
action→outcome and passes the supervisor as actor.
"""
from __future__ import annotations

import datetime as dt
import uuid

import sqlalchemy as sa

from conduit.shared.engine import runner, spine
from conduit.shared.engine import timers as _t
from conduit.shared.models import (
    Escalation,
    EscalationLadder,
    IssueCode,
    Property,
    Recommendation,
    RecReassign,
    Request,
    Roster,
    RosterAssignment,
    Room,
    Section,
    SLAPreset,
    StaffProfile,
    Stay,
    Timer,
    WorkOrder,
)

_PW = "pw-123456"


async def _seed_world(db, make_account):
    """Property→Section→Room, an active P3 SLAPreset, a dispatch IssueCode
    (skill_matched so the stall recommendation is a deterministic reassign),
    an active EscalationLadder (the spine precondition). A duty manager is
    referenced by the ladder."""
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
    sla = SLAPreset(property_id=p.id, tier="P3", accept_window_seconds=120,
                    fulfilment_sla_seconds=1800, supervisor_sla_seconds=900,
                    status="active")
    db.add(sla)
    await db.flush()
    ic = IssueCode(code=f"IC-{uuid.uuid4().hex[:6]}", label="Towels",
                   department="housekeeping", fulfilment_mode="dispatch",
                   routing_model="skill_matched", sla_preset_id=sla.id)
    db.add(ic)
    await db.flush()
    db.add(EscalationLadder(property_id=p.id,
                            duty_manager_account_id=duty.id,
                            n_cycle_bound=3, status="active"))
    await db.flush()
    return p, sec, room, ic, duty


async def _open_stall_escalation(db, make_account, p, sec, room, ic):
    """A routed dispatch WorkOrder + an open *stall* Escalation produced by
    the real ``spine.open_escalation`` (recommendation + rec_* detail +
    supervisor_sla Timer all spine-built). Returns handles."""
    owner = await make_account("servicer", f"ow-{uuid.uuid4().hex[:8]}", _PW)
    stalled = await make_account("servicer", f"st-{uuid.uuid4().hex[:8]}", _PW)
    target = await make_account("servicer", f"tg-{uuid.uuid4().hex[:8]}", _PW)
    guest = await make_account("guest", f"g-{uuid.uuid4().hex[:8]}", _PW)

    now = dt.datetime.now(dt.timezone.utc)
    stay = Stay(guest_account_id=guest.id, room_id=room.id, check_in=now,
                check_out=now + dt.timedelta(days=1), status="active")
    db.add(stay)
    await db.flush()
    req = Request(guest_account_id=guest.id, stay_id=stay.id, raw_text="x")
    db.add(req)
    await db.flush()
    from conduit.shared.models import ChildSubRequest
    child = ChildSubRequest(request_id=req.id, text="x", outcome="auto",
                            fulfilment_mode="dispatch", issue_code_id=ic.id,
                            state="in_progress", priority_tier="P3")
    db.add(child)
    await db.flush()
    wo = WorkOrder(child_id=child.id, kind="dispatch",
                   routing_model="skill_matched", priority_tier="P3",
                   assigned_servicer_id=stalled.id,
                   accountable_owner_id=owner.id,
                   section_id=sec.id, state="created")
    db.add(wo)
    await db.flush()

    # The fresh non-stalled servicer C1 routing.select will pick.
    db.add(StaffProfile(account_id=target.id, staff_class="housekeeping",
                        presence="working", status="active"))
    roster = Roster(property_id=p.id,
                    shift_start=now - dt.timedelta(hours=1),
                    shift_end=now + dt.timedelta(hours=8), status="active")
    db.add(roster)
    await db.flush()
    db.add(RosterAssignment(roster_id=roster.id, account_id=target.id,
                            section_id=sec.id, assignment="member",
                            status="active"))
    await db.flush()

    esc = await spine.open_escalation(
        db, child, spine.EscalationTrigger.STALL,
        stalled_account_id=stalled.id)
    await db.flush()
    return {"child": child, "wo": wo, "esc": esc, "owner": owner,
            "stalled": stalled, "target": target}


async def test_supervisor_decisions_spine(client, make_account, login, db):
    p, sec, room, ic, duty = await _seed_world(db, make_account)
    sup = await make_account("supervisor", f"sup-{uuid.uuid4().hex[:8]}", _PW)

    h1 = await _open_stall_escalation(db, make_account, p, sec, room, ic)
    h2 = await _open_stall_escalation(db, make_account, p, sec, room, ic)
    h_edit = await _open_stall_escalation(db, make_account, p, sec, room, ic)

    # A hard-escalated (duty-manager, non-time-boxed) escalation — flagged.
    h_hard = await _open_stall_escalation(db, make_account, p, sec, room, ic)
    await spine.hard_escalate(db, h_hard["esc"])
    await db.flush()
    # But h_hard's escalation is now resolved/terminal; build a SEPARATE
    # open one whose ladder makes it duty-manager (non-time-boxed) flagged
    # at the open stage is impossible — the queue flags the resolved
    # hard_escalated state on a *closed* item only when ?status filters
    # include it. Keep it simple: assert the open queue excludes it.
    await db.commit()

    # ---- No cookie → 401 -------------------------------------------------
    r = await client.get("/api/supervisor/decisions")
    assert r.status_code == 401, r.text

    # ---- Wrong role: guest cookie → 403 ----------------------------------
    g = await make_account("guest", f"wg-{uuid.uuid4().hex[:8]}", _PW)
    await login(g.username, _PW)
    rg = await client.get("/api/supervisor/decisions")
    assert rg.status_code == 403, rg.text
    # Wrong role: servicer cookie → 403
    sv = await make_account("servicer", f"ws-{uuid.uuid4().hex[:8]}", _PW)
    await login(sv.username, _PW)
    rs = await client.post(
        f"/api/supervisor/decisions/{h1['esc'].id}/resolve",
        json={"action": "approve"})
    assert rs.status_code == 403, rs.text

    # ---- GET /api/supervisor/decisions → 200, lists open escalations -----
    await login(sup.username, _PW)
    lst = await client.get("/api/supervisor/decisions")
    assert lst.status_code == 200, lst.text
    body = lst.json()
    by_id = {d["escalation_id"]: d for d in body}
    assert str(h1["esc"].id) in by_id
    assert str(h2["esc"].id) in by_id
    # The resolved (hard_escalated) one is NOT in the open queue.
    assert str(h_hard["esc"].id) not in by_id
    card = by_id[str(h1["esc"].id)]
    assert card["state"] == "open"
    assert card["trigger"] == "stall"
    assert card["cycle_count"] == 0
    assert card["recommendation"]["action"] == "reassign"
    # Per-action detail surfaced (the stored rec_reassign target).
    assert card["recommendation"]["detail"]["target_account_id"] == \
        str(h1["target"].id)
    # Supervisor-SLA countdown DEADLINE (ISO) present + time-boxed.
    assert card["supervisor_sla_deadline"] is not None
    assert card["non_time_boxed"] is False
    # No internal leak — curated keys only.
    assert set(card.keys()) == {
        "escalation_id", "child_id", "trigger", "state", "cycle_count",
        "supervisor_sla_deadline", "non_time_boxed", "recommendation",
        "issue_label"}

    # ---- ?status filter is honoured (hard_escalated visible there) -------
    lst_h = await client.get("/api/supervisor/decisions?status=hard_escalated")
    assert lst_h.status_code == 200, lst_h.text
    hbody = {d["escalation_id"]: d for d in lst_h.json()}
    assert str(h_hard["esc"].id) in hbody
    assert hbody[str(h_hard["esc"].id)]["non_time_boxed"] is True

    # ---- bad payload: edit with missing required action → 422 ------------
    rbad = await client.post(
        f"/api/supervisor/decisions/{h_edit['esc'].id}/resolve",
        json={"action": "edit"})
    assert rbad.status_code == 422, rbad.text
    # unknown extra key → 422 (extra="forbid")
    rbad2 = await client.post(
        f"/api/supervisor/decisions/{h1['esc'].id}/resolve",
        json={"action": "approve", "bogus": 1})
    assert rbad2.status_code == 422, rbad2.text
    # unknown action enum → 422
    rbad3 = await client.post(
        f"/api/supervisor/decisions/{h1['esc'].id}/resolve",
        json={"action": "nope"})
    assert rbad3.status_code == 422, rbad3.text

    # ---- POST resolve {action:"edit", payload:{...}} → 200 ---------------
    # Override the stored reassign target with a supervisor-supplied one
    # (the OWNER account), proving the supplied action/payload — NOT the
    # stored rec — is executed.
    redit = await client.post(
        f"/api/supervisor/decisions/{h_edit['esc'].id}/resolve",
        json={"action": "edit", "payload": {
            "action": "reassign",
            "target_account_id": str(h_edit["owner"].id)}})
    assert redit.status_code == 200, redit.text
    await db.commit()
    e_edit = (await db.execute(sa.select(Escalation).where(
        Escalation.id == h_edit["esc"].id))).scalar_one()
    assert e_edit.state == "edited"
    assert str(e_edit.resolved_by_account_id) == str(sup.id)
    wo_edit = (await db.execute(sa.select(WorkOrder).where(
        WorkOrder.id == h_edit["wo"].id))).scalar_one()
    # Supervisor-supplied target won (NOT the stored rec target).
    assert str(wo_edit.assigned_servicer_id) == str(h_edit["owner"].id)

    # ---- POST resolve {action:"approve"} → 200 via the spine -------------
    rok = await client.post(
        f"/api/supervisor/decisions/{h1['esc'].id}/resolve",
        json={"action": "approve"})
    assert rok.status_code == 200, rok.text
    await db.commit()
    e1 = (await db.execute(sa.select(Escalation).where(
        Escalation.id == h1["esc"].id))).scalar_one()
    assert e1.state == "approved"
    assert str(e1.resolved_by_account_id) == str(sup.id)
    assert e1.resolved_at is not None

    # ---- resolving an already-resolved escalation → 409 ------------------
    r409 = await client.post(
        f"/api/supervisor/decisions/{h1['esc'].id}/resolve",
        json={"action": "approve"})
    assert r409.status_code == 409, r409.text

    # ---- foreign / random uuid → 409 (no open escalation) ----------------
    rno = await client.post(
        f"/api/supervisor/decisions/{uuid.uuid4()}/resolve",
        json={"action": "approve"})
    assert rno.status_code == 409, rno.text

    # ---- DELETE any decisions route → 405 --------------------------------
    rd = await client.delete(
        f"/api/supervisor/decisions/{h2['esc'].id}/resolve")
    assert rd.status_code == 405, rd.text
    rd2 = await client.delete("/api/supervisor/decisions")
    assert rd2.status_code == 405, rd2.text

    # =====================================================================
    # SYMMETRY: silence ≡ approve is STRUCTURAL.
    # h2 → resolved via the API (approve).  h_sym → driven by the engine
    # auto-proceed path (runner.tick after arming its supervisor_sla timer
    # in the past). Both call the SAME spine.apply_recommendation. The end
    # state MUST be identical EXCEPT resolved_by_account_id.
    # =====================================================================
    h_sym = await _open_stall_escalation(db, make_account, p, sec, room, ic)
    await db.commit()

    # API-approve h2.
    rsym = await client.post(
        f"/api/supervisor/decisions/{h2['esc'].id}/resolve",
        json={"action": "approve"})
    assert rsym.status_code == 200, rsym.text
    await db.commit()

    # Drive h_sym through the engine auto-proceed (NO API call): arm its
    # supervisor_sla timer in the past, then runner.tick.
    db_now = (await db.execute(sa.select(sa.func.now()))).scalar_one()
    # Cancel the spine-armed (future) supervisor_sla timer then arm one in
    # the past so the runner claims it (the D3 mechanism).
    await db.execute(sa.update(Timer).where(
        Timer.escalation_id == h_sym["esc"].id,
        Timer.type == "supervisor_sla",
        Timer.state == "pending").values(state="cancelled"))
    await _t.arm(db, "escalation_id", h_sym["esc"].id,
                 _t.TimerType.SUPERVISOR_SLA,
                 fire_at=db_now - dt.timedelta(seconds=5))
    await db.flush()
    fired = await runner.tick(db)
    assert fired >= 1
    await db.commit()

    e_api = (await db.execute(sa.select(Escalation).where(
        Escalation.id == h2["esc"].id))).scalar_one()
    e_auto = (await db.execute(sa.select(Escalation).where(
        Escalation.id == h_sym["esc"].id))).scalar_one()
    wo_api = (await db.execute(sa.select(WorkOrder).where(
        WorkOrder.id == h2["wo"].id))).scalar_one()
    wo_auto = (await db.execute(sa.select(WorkOrder).where(
        WorkOrder.id == h_sym["wo"].id))).scalar_one()
    c_api = (await db.execute(sa.select(type(h2["child"])).where(
        type(h2["child"]).id == h2["child"].id))).scalar_one()
    c_auto = (await db.execute(sa.select(type(h_sym["child"])).where(
        type(h_sym["child"]).id == h_sym["child"].id))).scalar_one()

    # Identical WorkOrder effect: BOTH paths execute the STORED
    # recommendation verbatim (approve and auto_proceeded are the
    # ``_STORED_REC_OUTCOMES`` set — silence ≡ approve is structural), so
    # each WO's assignee MUST equal ITS OWN escalation's stored
    # ``rec_reassign`` target (the C1-routed pick captured at open time).
    rec_api = (await db.execute(sa.select(RecReassign).where(
        RecReassign.recommendation_escalation_id == h2["esc"].id)
    )).scalar_one()
    rec_auto = (await db.execute(sa.select(RecReassign).where(
        RecReassign.recommendation_escalation_id == h_sym["esc"].id)
    )).scalar_one()
    assert str(wo_api.assigned_servicer_id) == \
        str(rec_api.target_account_id)
    assert str(wo_auto.assigned_servicer_id) == \
        str(rec_auto.target_account_id)
    # The accountable owner is UNCHANGED across the resolve (D12) in BOTH
    # the API and the engine auto-proceed path.
    assert str(wo_api.accountable_owner_id) == str(h2["owner"].id)
    assert str(wo_auto.accountable_owner_id) == str(h_sym["owner"].id)
    # Identical child state.
    assert c_api.state == c_auto.state
    # Identical cycle bump.
    assert e_api.cycle_count == e_auto.cycle_count == 1
    # The ONLY differences: outcome state + resolved_by_account_id.
    assert e_api.state == "approved"
    assert e_auto.state == "auto_proceeded"
    assert str(e_api.resolved_by_account_id) == str(sup.id)
    assert e_auto.resolved_by_account_id is None
    # Everything else symmetric.
    assert e_api.trigger == e_auto.trigger == "stall"
    assert e_api.resolved_at is not None and e_auto.resolved_at is not None


# ==========================================================================
# Task E4 — Supervisor task explorer + override (D6 god-mode, Spec §8).
#
# APPEND-only: the E3 tests above are preserved verbatim. This block reuses
# the E3 seed/cookie idiom (``_seed_world`` / ``_open_stall_escalation`` /
# the per-role ``login`` cookie chain) and proves the D6 interrupt-from-any
# -state contract: the three override actions act from a NON-trivial mid
# -state (an ``in_progress`` child with a routed WorkOrder + an OPEN
# escalation + an OPEN glitch) — NOT a special bypass node, just the C4
# guarded ``transition`` (cancel) + the established D2/D6 in-place
# WorkOrder assignee mutation (takeover/reassign). An illegal terminal
# transition (cancel an already-closed child) still 409s — god-mode = act
# from any *active* state, never violate the machine.
# ==========================================================================
async def _mid_state_child(db, make_account, p, sec, room, ic):
    """A child wedged mid-lifecycle: ``in_progress`` with a routed
    WorkOrder (assignee + accountable owner), an OPEN spine Escalation, and
    an OPEN Glitch — the worst-case "supervisor must reach in and act"
    shape. Returns handles."""
    from conduit.shared.models import ChildSubRequest, Glitch

    h = await _open_stall_escalation(db, make_account, p, sec, room, ic)
    gl = Glitch(child_id=h["child"].id, opened_from="problem_report",
                state="open")
    db.add(gl)
    await db.flush()
    h["glitch"] = gl
    return h


async def test_supervisor_children_explorer_and_override(
    client, make_account, login, db
):
    p, sec, room, ic, duty = await _seed_world(db, make_account)
    sup = await make_account("supervisor", f"sup-{uuid.uuid4().hex[:8]}", _PW)

    h_get = await _mid_state_child(db, make_account, p, sec, room, ic)
    h_to = await _mid_state_child(db, make_account, p, sec, room, ic)
    h_re = await _mid_state_child(db, make_account, p, sec, room, ic)
    h_ca = await _mid_state_child(db, make_account, p, sec, room, ic)
    h_409 = await _mid_state_child(db, make_account, p, sec, room, ic)
    # A target servicer the supervisor will reassign / hand-to.
    tgt = await make_account("servicer", f"rt-{uuid.uuid4().hex[:8]}", _PW)
    await db.commit()

    # ---- No cookie → 401 -------------------------------------------------
    r = await client.get("/api/supervisor/children")
    assert r.status_code == 401, r.text
    r = await client.post(
        f"/api/supervisor/children/{h_to['child'].id}/takeover", json={})
    assert r.status_code == 401, r.text

    # ---- Wrong role: guest / servicer cookie → 403 -----------------------
    g = await make_account("guest", f"wg-{uuid.uuid4().hex[:8]}", _PW)
    await login(g.username, _PW)
    assert (await client.get(
        "/api/supervisor/children")).status_code == 403
    sv = await make_account("servicer", f"ws-{uuid.uuid4().hex[:8]}", _PW)
    await login(sv.username, _PW)
    assert (await client.post(
        f"/api/supervisor/children/{h_ca['child'].id}/cancel",
        json={})).status_code == 403

    # ---- GET /api/supervisor/children → 200, global (sees everything) ----
    await login(sup.username, _PW)
    lst = await client.get("/api/supervisor/children")
    assert lst.status_code == 200, lst.text
    body = lst.json()
    by_id = {row["child_id"]: row for row in body}
    assert str(h_get["child"].id) in by_id
    card = by_id[str(h_get["child"].id)]
    assert card["state"] == "in_progress"
    assert card["work_order"]["assigned_servicer_id"] == \
        str(h_get["stalled"].id)
    assert card["work_order"]["accountable_owner_id"] == \
        str(h_get["owner"].id)
    assert card["escalation"]["state"] == "open"
    assert card["escalation"]["trigger"] == "stall"
    assert card["glitch"]["state"] == "open"
    # Curated keys only — no internal leak.
    assert set(card.keys()) == {
        "child_id", "state", "work_order", "escalation", "glitch",
        "issue_label"}

    # ---- filter param (?child_id=) narrows the global read --------------
    one = await client.get(
        f"/api/supervisor/children?child_id={h_get['child'].id}")
    assert one.status_code == 200, one.text
    obody = one.json()
    assert {row["child_id"] for row in obody} == {str(h_get["child"].id)}
    # filter by state
    st = await client.get("/api/supervisor/children?state=in_progress")
    assert st.status_code == 200, st.text
    assert all(row["state"] == "in_progress" for row in st.json())
    assert str(h_get["child"].id) in {r["child_id"] for r in st.json()}

    # ---- POST takeover → 200, in-place assignee swap from a mid-state ----
    # Default takeover hands the WorkOrder to the acting supervisor; the
    # accountable owner is UNCHANGED (D12). Acts from ``in_progress``
    # (D6 interrupt-from-any-active-state — proves it is NOT a bypass node).
    rt = await client.post(
        f"/api/supervisor/children/{h_to['child'].id}/takeover", json={})
    assert rt.status_code == 200, rt.text
    await db.commit()
    wo_to = (await db.execute(sa.select(WorkOrder).where(
        WorkOrder.id == h_to["wo"].id))).scalar_one()
    assert str(wo_to.assigned_servicer_id) == str(sup.id)
    assert str(wo_to.accountable_owner_id) == str(h_to["owner"].id)
    c_to = (await db.execute(sa.select(type(h_to["child"])).where(
        type(h_to["child"]).id == h_to["child"].id))).scalar_one()
    assert c_to.state == "in_progress"  # assignee swap is NOT a state change

    # takeover with an explicit target → hands to that servicer.
    rt2 = await client.post(
        f"/api/supervisor/children/{h_get['child'].id}/takeover",
        json={"target_servicer_id": str(tgt.id)})
    assert rt2.status_code == 200, rt2.text
    await db.commit()
    wo_get = (await db.execute(sa.select(WorkOrder).where(
        WorkOrder.id == h_get["wo"].id))).scalar_one()
    assert str(wo_get.assigned_servicer_id) == str(tgt.id)
    assert str(wo_get.accountable_owner_id) == str(h_get["owner"].id)

    # ---- POST reassign → 200, in-place to an explicit target ------------
    rr = await client.post(
        f"/api/supervisor/children/{h_re['child'].id}/reassign",
        json={"target_servicer_id": str(tgt.id)})
    assert rr.status_code == 200, rr.text
    await db.commit()
    wo_re = (await db.execute(sa.select(WorkOrder).where(
        WorkOrder.id == h_re["wo"].id))).scalar_one()
    assert str(wo_re.assigned_servicer_id) == str(tgt.id)
    assert str(wo_re.accountable_owner_id) == str(h_re["owner"].id)

    # ---- POST cancel → 200, child cancelled from a mid (in_progress) ----
    from conduit.shared.models import EventChildCancelled

    rc = await client.post(
        f"/api/supervisor/children/{h_ca['child'].id}/cancel", json={})
    assert rc.status_code == 200, rc.text
    await db.commit()
    c_ca = (await db.execute(sa.select(type(h_ca["child"])).where(
        type(h_ca["child"]).id == h_ca["child"].id))).scalar_one()
    assert c_ca.state == "cancelled"
    # Exactly ONE child_cancelled event (the C4 single-writer path).
    n_evt = (await db.execute(
        sa.select(sa.func.count()).select_from(EventChildCancelled)
        .where(EventChildCancelled.child_id == h_ca["child"].id)
    )).scalar_one()
    assert n_evt == 1

    # ---- no-op: cancel an already-closed/terminal child → 409 -----------
    # First cancel h_409, then cancel it AGAIN: the second is an illegal
    # transition (cancelled has no outgoing edge) — god-mode does NOT
    # bypass the machine's legality.
    assert (await client.post(
        f"/api/supervisor/children/{h_409['child'].id}/cancel",
        json={})).status_code == 200
    await db.commit()
    again = await client.post(
        f"/api/supervisor/children/{h_409['child'].id}/cancel", json={})
    assert again.status_code == 409, again.text

    # ---- unknown child → 404 --------------------------------------------
    assert (await client.post(
        f"/api/supervisor/children/{uuid.uuid4()}/takeover",
        json={})).status_code == 404
    assert (await client.post(
        f"/api/supervisor/children/{uuid.uuid4()}/cancel",
        json={})).status_code == 404

    # ---- malformed body (extra="forbid") → 422 --------------------------
    assert (await client.post(
        f"/api/supervisor/children/{h_to['child'].id}/reassign",
        json={"bogus": 1})).status_code == 422

    # ---- DELETE any children route → 405 --------------------------------
    assert (await client.delete(
        "/api/supervisor/children")).status_code == 405
    assert (await client.delete(
        f"/api/supervisor/children/{h_to['child'].id}/takeover"
    )).status_code == 405


# ==========================================================================
# Task B6 — the relocate decision card (`detail` enrichment) + the `edit`
# `{new_room_id}` variant (Spec §8 / §7.3 / §7.4). APPEND-only: every test
# above is preserved verbatim. The relocate escalation is produced by the
# REAL ``spine.open_escalation`` (SERVICER_RAISED) so the recommendation +
# its persisted ``RecRelocate.target_room_id`` + the supervisor_sla Timer
# are all spine-built (the deterministic available-room pick the pure
# ``room_selection`` computed at recommendation-build — never re-run here).
# ==========================================================================
async def _open_relocate_escalation(db, make_account, p, sec, room, ic,
                                     *, rooms):
    """An open *servicer_raised* relocate Escalation built by the REAL
    ``spine.open_escalation`` over a guest whose stay sits in ``room`` while
    ``rooms`` (extra empty rooms in the same property) provide the eligible
    available targets. The deterministic pick is persisted on
    ``RecRelocate.target_room_id`` at build. Returns handles incl. the
    guest's stay so the test can assert the re-bind."""
    from conduit.shared.models import ChildSubRequest

    owner = await make_account("servicer", f"ow-{uuid.uuid4().hex[:8]}", _PW)
    guest = await make_account("guest", f"g-{uuid.uuid4().hex[:8]}", _PW)
    now = dt.datetime.now(dt.timezone.utc)
    stay = Stay(guest_account_id=guest.id, room_id=room.id, check_in=now,
                check_out=now + dt.timedelta(days=1), status="active")
    db.add(stay)
    await db.flush()
    req = Request(guest_account_id=guest.id, stay_id=stay.id, raw_text="x")
    db.add(req)
    await db.flush()
    child = ChildSubRequest(request_id=req.id, text="x", outcome="auto",
                            fulfilment_mode="dispatch", issue_code_id=ic.id,
                            state="in_progress", priority_tier="P3")
    db.add(child)
    await db.flush()
    wo = WorkOrder(child_id=child.id, kind="dispatch",
                   routing_model="skill_matched", priority_tier="P3",
                   assigned_servicer_id=owner.id,
                   accountable_owner_id=owner.id,
                   section_id=sec.id, state="created")
    db.add(wo)
    await db.flush()
    esc = await spine.open_escalation(
        db, child, spine.EscalationTrigger.SERVICER_RAISED,
        actor_account_id=owner.id, reason="can't fix")
    await db.flush()
    return {"child": child, "wo": wo, "esc": esc, "owner": owner,
            "guest": guest, "stay": stay}


async def test_supervisor_relocate_decision_card_and_edit(
    client, make_account, login, db
):
    p, sec, room, ic, duty = await _seed_world(db, make_account)
    sup = await make_account("supervisor", f"sup-{uuid.uuid4().hex[:8]}", _PW)

    # Three spare rooms in the property: the deterministic pick is the FIRST
    # eligible (room_selection orders by label then id). Use disjoint labels
    # so the ordering is unambiguous.
    spare_a = Room(section_id=sec.id, label="RA")
    spare_b = Room(section_id=sec.id, label="RB")
    spare_c = Room(section_id=sec.id, label="RC")
    db.add_all([spare_a, spare_b, spare_c])
    await db.flush()

    # An OCCUPIED room (an active stay binds it) — the edit-409 case.
    occ_room = Room(section_id=sec.id, label="ROCC")
    db.add(occ_room)
    await db.flush()
    occ_guest = await make_account("guest", f"og-{uuid.uuid4().hex[:8]}", _PW)
    now = dt.datetime.now(dt.timezone.utc)
    db.add(Stay(guest_account_id=occ_guest.id, room_id=occ_room.id,
                check_in=now, check_out=now + dt.timedelta(days=1),
                status="active"))
    await db.flush()

    h = await _open_relocate_escalation(
        db, make_account, p, sec, room, ic,
        rooms=[spare_a, spare_b, spare_c])
    h_edit = await _open_relocate_escalation(
        db, make_account, p, sec, room, ic,
        rooms=[spare_a, spare_b, spare_c])
    await db.commit()

    # The spine persisted the deterministic relocate target.
    from conduit.shared.models import RecRelocate
    rr = (await db.execute(sa.select(RecRelocate).where(
        RecRelocate.recommendation_escalation_id == h["esc"].id)
    )).scalar_one()
    persisted_target = rr.target_room_id

    # ---- GET /api/supervisor/decisions → the relocate detail card --------
    await login(sup.username, _PW)
    lst = await client.get("/api/supervisor/decisions")
    assert lst.status_code == 200, lst.text
    by_id = {d["escalation_id"]: d for d in lst.json()}
    card = by_id[str(h["esc"].id)]
    assert card["recommendation"]["action"] == "relocate"
    detail = card["recommendation"]["detail"]
    # The supervisor decision-card data (Spec §8): current / recommended /
    # eligible rooms. ``recommended_room`` == the persisted
    # ``RecRelocate.target_room_id`` projection (display-only; selection is
    # NOT re-run to mutate the recommendation — auto-proceed safety).
    assert detail["current_room"] == str(room.id)
    assert detail["recommended_room"] == str(persisted_target)
    assert isinstance(detail["eligible_rooms"], list)
    elig = set(detail["eligible_rooms"])
    assert {str(spare_a.id), str(spare_b.id), str(spare_c.id)} <= elig
    # Occupied + current are NOT eligible.
    assert str(occ_room.id) not in elig
    assert str(room.id) not in elig
    # The thin stored projection is still carried (B-line preservation).
    assert detail["target_room_id"] == str(persisted_target)
    # A non-relocate item is unchanged (no new keys).
    h_stall = await _open_stall_escalation(db, make_account, p, sec, room, ic)
    await db.commit()
    lst2 = await client.get("/api/supervisor/decisions")
    s_card = {d["escalation_id"]: d for d in lst2.json()}[
        str(h_stall["esc"].id)]
    assert s_card["recommendation"]["action"] == "reassign"
    assert "current_room" not in s_card["recommendation"]["detail"]

    # ---- edit with an UNKNOWN room id → 422 ------------------------------
    r422 = await client.post(
        f"/api/supervisor/decisions/{h_edit['esc'].id}/resolve",
        json={"action": "edit", "payload": {"new_room_id": str(uuid.uuid4())}})
    assert r422.status_code == 422, r422.text

    # ---- edit to an OCCUPIED room → 409 ----------------------------------
    r409 = await client.post(
        f"/api/supervisor/decisions/{h_edit['esc'].id}/resolve",
        json={"action": "edit", "payload": {"new_room_id": str(occ_room.id)}})
    assert r409.status_code == 409, r409.text

    # ---- edit to the CURRENT room → 409 ----------------------------------
    r409b = await client.post(
        f"/api/supervisor/decisions/{h_edit['esc'].id}/resolve",
        json={"action": "edit", "payload": {"new_room_id": str(room.id)}})
    assert r409b.status_code == 409, r409b.text

    # ---- edit to an eligible room (NOT the recommended one) → 200 --------
    # Pick a spare that is NOT the deterministic recommended target so the
    # supervisor-edited room is provably what re-binds (not the stored rec).
    chosen = (spare_b if str(spare_b.id) != str(persisted_target)
              else spare_c)
    redit = await client.post(
        f"/api/supervisor/decisions/{h_edit['esc'].id}/resolve",
        json={"action": "edit", "payload": {"new_room_id": str(chosen.id)}})
    assert redit.status_code == 200, redit.text
    await db.commit()
    e_edit = (await db.execute(sa.select(Escalation).where(
        Escalation.id == h_edit["esc"].id))).scalar_one()
    assert e_edit.state == "edited"
    assert str(e_edit.resolved_by_account_id) == str(sup.id)
    # The REAL relocate_stay re-bound the guest's stay to the CHOSEN room
    # (the single executor — NOT reimplemented here).
    stay_row = (await db.execute(sa.select(Stay).where(
        Stay.id == h_edit["stay"].id))).scalar_one()
    assert str(stay_row.room_id) == str(chosen.id)

    # ---- approve a relocate → re-binds to the persisted target ----------
    rok = await client.post(
        f"/api/supervisor/decisions/{h['esc'].id}/resolve",
        json={"action": "approve"})
    assert rok.status_code == 200, rok.text
    await db.commit()
    e_ok = (await db.execute(sa.select(Escalation).where(
        Escalation.id == h["esc"].id))).scalar_one()
    assert e_ok.state == "approved"
    stay_ok = (await db.execute(sa.select(Stay).where(
        Stay.id == h["stay"].id))).scalar_one()
    assert str(stay_ok.room_id) == str(persisted_target)

    # ---- an already-resolved relocate escalation → 409 (preserved) ------
    r409c = await client.post(
        f"/api/supervisor/decisions/{h['esc'].id}/resolve",
        json={"action": "approve"})
    assert r409c.status_code == 409, r409c.text
