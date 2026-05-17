"""Task E6 — Supervisor awareness stream: the FIRST event read model
(Spec §8/§9, the deferred read side finally consumed).

ONE full-ASGI scripted test over the merged per-test ``client`` with the
proven per-role cookie chain (``login`` swaps the single active session
cookie — the idiom in ``test_supervisor_decisions`` /
``test_servicer_tasks`` / ``test_staffing_api``).

Genuine ``event``+detail rows are produced by driving the REAL spine /
C4 single-writer path (NEVER hand-inserting events): a routed dispatch +
an open *stall* ``Escalation`` via ``spine.open_escalation`` (emits
``escalation_opened``); a WorkOrder driven created→pushed→accepted→
in_progress→completed via the C4 ``lifecycle.transition`` single writer
(emits ``work_order_*`` + a ``cross_dept_notified`` on completion); a
``Glitch`` opened then closed via the same ``lifecycle.transition``
(emits ``glitch_opened`` then ``glitch_closed``).

The slice's reason to exist: ``GET /api/supervisor/awareness`` returns ONE
composite projection of FOUR sections (incoming · task delegation ·
servicer recent work · open glitches), and every projected item
corresponds to an EMITTED EVENT (not a direct core-table SELECT). The
critical proof: a Glitch shows in "open glitches" while its
``glitch_opened`` has no matching ``glitch_closed``, and DISAPPEARS once a
``glitch_closed`` is driven through the real path (opened-minus-closed,
event-log-derived).
"""
from __future__ import annotations

import datetime as dt
import uuid

from conduit.shared.domain import lifecycle
from conduit.shared.engine import spine
from conduit.shared.models import (ChildSubRequest, Glitch, IssueCode,
                                   Property, Request, Room, Section,
                                   SLAPreset, Stay, WorkOrder)

_PW = "pw-123456"


async def _seed_world(db, make_account):
    """Property→Section→Room, an active P3 SLAPreset, a dispatch IssueCode,
    an active EscalationLadder (the spine precondition)."""
    from conduit.shared.models import EscalationLadder

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
    return p, sec, room, ic


async def _child_with_wo(db, make_account, p, sec, room, ic):
    """A routed dispatch child + its WorkOrder (state ``created``)."""
    guest = await make_account("guest", f"g-{uuid.uuid4().hex[:8]}", _PW)
    svc = await make_account("servicer", f"sv-{uuid.uuid4().hex[:8]}", _PW)
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
                   assigned_servicer_id=svc.id, accountable_owner_id=svc.id,
                   section_id=sec.id, state="created")
    db.add(wo)
    await db.flush()
    return {"child": child, "wo": wo, "servicer": svc}


async def test_supervisor_awareness_stream(client, make_account, login, db):
    p, sec, room, ic = await _seed_world(db, make_account)
    sup = await make_account("supervisor", f"sup-{uuid.uuid4().hex[:8]}", _PW)

    # --- incoming: an OPEN stall escalation via the REAL spine -------------
    h_esc = await _child_with_wo(db, make_account, p, sec, room, ic)
    esc = await spine.open_escalation(
        db, h_esc["child"], spine.EscalationTrigger.STALL,
        stalled_account_id=h_esc["servicer"].id)
    await db.flush()

    # --- task delegation + servicer recent work: drive a WO through the
    #     C4 single writer (created->pushed->accepted->in_progress->
    #     completed); completion emits cross_dept_notified via ctx ----------
    h_wo = await _child_with_wo(db, make_account, p, sec, room, ic)
    wo = h_wo["wo"]
    await lifecycle.transition(db, wo, "pushed")
    await lifecycle.transition(db, wo, "accepted")
    await lifecycle.transition(db, wo, "in_progress")
    await lifecycle.transition(db, wo, "completed",
                               target_department="engineering",
                               xdn_reason="work_order_completed")
    await db.flush()

    # --- open glitches: a Glitch opened via the C4 single writer ----------
    h_gl = await _child_with_wo(db, make_account, p, sec, room, ic)
    gl = Glitch(child_id=h_gl["child"].id, opened_from="problem_report",
                state="open")
    db.add(gl)
    await db.flush()
    # ``open`` is the Glitch start state (no ``*->open`` machine edge), so
    # — exactly as the spine emits ``escalation_opened`` for a freshly
    # created Escalation — the new-entity ``glitch_opened`` is appended via
    # the same merged writer (the single append-only event-log writer; no
    # parallel writer is invented).
    from conduit.shared.events import writer as _w
    await _w.emit_glitch_opened(db, gl.id)
    await db.flush()
    await db.commit()

    # ---- No cookie → 401 -------------------------------------------------
    r = await client.get("/api/supervisor/awareness")
    assert r.status_code == 401, r.text

    # ---- Wrong role: guest / servicer cookie → 403 -----------------------
    g = await make_account("guest", f"wg-{uuid.uuid4().hex[:8]}", _PW)
    await login(g.username, _PW)
    assert (await client.get(
        "/api/supervisor/awareness")).status_code == 403
    sv = await make_account("servicer", f"ws-{uuid.uuid4().hex[:8]}", _PW)
    await login(sv.username, _PW)
    assert (await client.get(
        "/api/supervisor/awareness")).status_code == 403

    # ---- GET /api/supervisor/awareness → 200, ONE composite projection ---
    await login(sup.username, _PW)
    resp = await client.get("/api/supervisor/awareness")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # Exact composite key set — extra="forbid", no internal leak.
    assert set(body.keys()) == {
        "incoming", "task_delegation", "servicer_recent_work",
        "open_glitches"}

    # incoming ⟵ the emitted escalation_opened (still open).
    inc_ids = {row["escalation_id"] for row in body["incoming"]}
    assert str(esc.id) in inc_ids
    inc = next(r for r in body["incoming"]
               if r["escalation_id"] == str(esc.id))
    assert inc["child_id"] == str(h_esc["child"].id)
    assert inc["trigger"] == "stall"

    # task_delegation ⟵ the emitted work_order_pushed/accepted events.
    deleg = {row["work_order_id"]: row for row in body["task_delegation"]}
    assert str(wo.id) in deleg
    assert deleg[str(wo.id)]["child_id"] == str(h_wo["child"].id)

    # servicer_recent_work ⟵ the emitted work_order_completed/in_progress.
    recent = {row["work_order_id"]: row
              for row in body["servicer_recent_work"]}
    assert str(wo.id) in recent
    assert recent[str(wo.id)]["servicer_id"] == str(h_wo["servicer"].id)

    # open_glitches ⟵ glitch_opened with NO matching glitch_closed.
    open_gids = {row["glitch_id"] for row in body["open_glitches"]}
    assert str(gl.id) in open_gids
    og = next(r for r in body["open_glitches"]
              if r["glitch_id"] == str(gl.id))
    assert og["child_id"] == str(h_gl["child"].id)
    assert og["opened_from"] == "problem_report"

    # ---- DELETE → 405 ----------------------------------------------------
    assert (await client.delete(
        "/api/supervisor/awareness")).status_code == 405

    # =====================================================================
    # The opened-minus-closed proof: drive a glitch_closed through the REAL
    # C4 single writer (open -> closed) and re-GET — the glitch is GONE
    # from the event-log-derived "open glitches" projection.
    # =====================================================================
    await lifecycle.transition(db, gl, "closed")
    await db.flush()
    await db.commit()

    resp2 = await client.get("/api/supervisor/awareness")
    assert resp2.status_code == 200, resp2.text
    body2 = resp2.json()
    open_gids2 = {row["glitch_id"] for row in body2["open_glitches"]}
    assert str(gl.id) not in open_gids2     # opened MINUS closed → gone
    # The other sections are unaffected (still event-derived, still there).
    assert str(esc.id) in {
        r["escalation_id"] for r in body2["incoming"]}
    assert str(wo.id) in {
        r["work_order_id"] for r in body2["task_delegation"]}
