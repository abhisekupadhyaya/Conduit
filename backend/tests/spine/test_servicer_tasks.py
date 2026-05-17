"""Task E2 — Servicer task queue + claim/accept/start/complete/raise.

Spec §8 (Servicer) + §9.2. ONE full-ASGI scripted test driven over the
merged per-test ``client`` with a real per-role cookie chain (``login``
swaps the single active session cookie — the proven idiom in
``test_e2e_journey`` / ``test_staffing_api`` / ``test_guest_dispatch``).

A rostered + working servicer is built via the merged staffing models so
``availability.effective_available`` is genuinely true now. The seven
servicer task surfaces are exercised end to end with the full status
matrix (200 / 201 / 401 / 403 / 404 / 409 / 405) plus cross-servicer
isolation (a second servicer must NOT see or act on the first's task).

Effecting is ONLY via the C4 ``lifecycle.transition`` writer + the spine
``open_escalation`` — nothing here re-implements routing/availability/spine.
``accountable_owner_id`` MUST stay unchanged across a claim (D12) — asserted.
"""
from __future__ import annotations

import datetime as dt
import uuid

import sqlalchemy as sa

from conduit.shared.models import (
    Account,
    ChildSubRequest,
    Escalation,
    EscalationLadder,
    Property,
    Recommendation,
    Request,
    Room,
    Roster,
    RosterAssignment,
    Section,
    SLAPreset,
    StaffProfile,
    Stay,
    Timer,
    WorkOrder,
)

_PW = "pw-123456"


async def _rostered_servicer(db, make_account, p, sec, *, owner=True,
                             section_id=None, suffix=""):
    """A servicer that is ``effective_available`` now: active StaffProfile
    (presence=working) + an active Roster window covering DB-now + an active
    RosterAssignment in ``section_id`` (defaults to ``sec``)."""
    srv = await make_account("servicer", f"sv-{suffix}-{uuid.uuid4().hex[:8]}",
                             _PW, display_name=f"Servicer {suffix}")
    db.add(StaffProfile(account_id=srv.id, staff_class="housekeeping",
                        presence="working", status="active"))
    now = dt.datetime.now(dt.timezone.utc)
    roster = Roster(property_id=p.id,
                    shift_start=now - dt.timedelta(hours=1),
                    shift_end=now + dt.timedelta(hours=8), status="active")
    db.add(roster)
    await db.flush()
    db.add(RosterAssignment(
        roster_id=roster.id, account_id=srv.id,
        section_id=section_id if section_id is not None else sec.id,
        assignment="owner" if owner else "member", status="active"))
    await db.flush()
    return srv


async def _make_wo(db, ic, sec, room, *, state, assigned, accountable):
    """A dispatch child + its WorkOrder at ``state`` (the C4-created shape),
    plus the two D23 timers armed against the child (accept_window +
    fulfilment_sla) so the queue can surface live deadlines."""
    guest = await make_guest(db)
    stay = (await db.execute(
        sa.select(Stay).where(Stay.guest_account_id == guest.id)
    )).scalar_one()
    req = Request(guest_account_id=guest.id, stay_id=stay.id, raw_text="x")
    db.add(req)
    await db.flush()
    child = ChildSubRequest(request_id=req.id, text="x", outcome="auto",
                            fulfilment_mode="dispatch", issue_code_id=ic.id,
                            state="routing")
    db.add(child)
    await db.flush()
    wo = WorkOrder(child_id=child.id, kind="dispatch",
                   routing_model="section_pooled", priority_tier="P3",
                   assigned_servicer_id=assigned,
                   accountable_owner_id=accountable,
                   section_id=sec.id, state=state)
    db.add(wo)
    await db.flush()
    now = dt.datetime.now(dt.timezone.utc)
    db.add(Timer(type="accept_window", child_id=child.id,
                 fire_at=now + dt.timedelta(seconds=120), state="pending"))
    db.add(Timer(type="fulfilment_sla", child_id=child.id,
                 fire_at=now + dt.timedelta(seconds=1800), state="pending"))
    await db.flush()
    return child, wo


_GUEST_ROOM: dict = {}


async def make_guest(db):
    acc = await _MK("guest", f"g-{uuid.uuid4().hex[:8]}", _PW)
    stay = Stay(guest_account_id=acc.id, room_id=_GUEST_ROOM["room_id"],
                check_in=dt.datetime.now(dt.timezone.utc),
                check_out=dt.datetime.now(dt.timezone.utc)
                + dt.timedelta(days=1),
                status="active")
    db.add(stay)
    await db.flush()
    return acc


_MK = None


async def _seed_world(db, make_account):
    """Property→Section→Room, an active P3 SLAPreset, a dispatch IssueCode,
    an active EscalationLadder (spine precondition)."""
    global _MK
    _MK = make_account
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
    _GUEST_ROOM["room_id"] = room.id
    sla = SLAPreset(property_id=p.id, tier="P3", accept_window_seconds=120,
                    fulfilment_sla_seconds=1800, supervisor_sla_seconds=900,
                    status="active")
    db.add(sla)
    await db.flush()
    ic = IssueCode(code="HK_TOWELS", label="Extra towels",
                   department="housekeeping", fulfilment_mode="dispatch",
                   routing_model="section_pooled", sla_preset_id=sla.id)
    db.add(ic)
    await db.flush()
    db.add(EscalationLadder(property_id=p.id,
                            duty_manager_account_id=duty.id,
                            n_cycle_bound=3, status="active"))
    await db.flush()
    return p, sec, room, ic


from conduit.shared.models import IssueCode  # noqa: E402


async def test_servicer_tasks_spine(client, make_account, login, db):
    p, sec, room, ic = await _seed_world(db, make_account)

    srv = await _rostered_servicer(db, make_account, p, sec, suffix="A")
    other_sec = Section(property_id=p.id, label="S2")
    db.add(other_sec)
    await db.flush()
    srv2 = await _rostered_servicer(db, make_account, p, other_sec,
                                    section_id=other_sec.id, suffix="B")

    # A pushed (owned) WO for srv; a broadcast (in-zone claimable) WO; a
    # broadcast WO in srv2's section (NOT in srv's zone).
    owned_child, owned_wo = await _make_wo(
        db, ic, sec, room, state="pushed",
        assigned=srv.id, accountable=srv.id)
    # The child rides the dispatch arc WorkOrder-carried (C4 emits NO child
    # event for the pushed/accepted/in_progress hops — the WorkOrder carries
    # the visible leg, E1 design). The child HOLDS at its REAL state
    # (``routing``, set by ``_make_wo`` — the real intake/routing shape); NO
    # test-side model write of a journey transition. On WO → completed the
    # §7.2 C4 hop carries the routing-held child → done_pending_confirm
    # (Spec §7.2 — NOT conditional on the child being in_progress). The
    # accept→start→complete walk below drives the WO via the REAL servicer
    # API.
    assert owned_child.state == "routing"
    # Broadcast WO in srv's zone (sec) but owned by srv2 — so it is
    # genuinely CLAIMABLE for srv (not owned by srv); claiming it must NOT
    # change its accountable owner (D12).
    bc_child, bc_wo = await _make_wo(
        db, ic, sec, room, state="broadcast",
        assigned=None, accountable=srv2.id)
    foreign_child, foreign_wo = await _make_wo(
        db, ic, other_sec, room, state="broadcast",
        assigned=None, accountable=srv2.id)
    await db.commit()
    bc_original_owner = bc_wo.accountable_owner_id  # == srv2.id (D12 invariant)

    # ---- No cookie → 401 -------------------------------------------------
    r = await client.get("/api/servicer/tasks")
    assert r.status_code == 401, r.text

    # ---- Wrong role (guest cookie) → 403 ---------------------------------
    g = await make_account("guest", f"wg-{uuid.uuid4().hex[:8]}", _PW)
    await login(g.username, _PW)
    rg = await client.get("/api/servicer/tasks")
    assert rg.status_code == 403, rg.text
    # Wrong role (supervisor cookie) → 403
    sup = await make_account("supervisor", f"ws-{uuid.uuid4().hex[:8]}", _PW)
    await login(sup.username, _PW)
    rs = await client.post(f"/api/servicer/tasks/{owned_wo.id}/accept")
    assert rs.status_code == 403, rs.text

    # ---- GET /api/servicer/tasks → 200, pushed + claimable ---------------
    await login(srv.username, _PW)
    lst = await client.get("/api/servicer/tasks")
    assert lst.status_code == 200, lst.text
    body = lst.json()
    by_id = {t["work_order_id"]: t for t in body}
    assert str(owned_wo.id) in by_id
    assert str(bc_wo.id) in by_id
    # Foreign section broadcast must NOT appear (zone-scoped claimable).
    assert str(foreign_wo.id) not in by_id
    owned_card = by_id[str(owned_wo.id)]
    assert owned_card["kind"] == "pushed"
    assert owned_card["state"] == "pushed"
    assert owned_card["accept_window_deadline"] is not None
    assert owned_card["fulfilment_sla_deadline"] is not None
    assert by_id[str(bc_wo.id)]["kind"] == "claimable"
    # No internal leakage — curated keys only.
    assert set(owned_card.keys()) == {
        "work_order_id", "child_id", "kind", "state", "priority_tier",
        "issue_label", "accept_window_deadline", "fulfilment_sla_deadline"}

    # ---- Cross-servicer isolation: srv2 must NOT see srv's pushed task ---
    await login(srv2.username, _PW)
    lst2 = await client.get("/api/servicer/tasks")
    assert lst2.status_code == 200, lst2.text
    ids2 = {t["work_order_id"] for t in lst2.json()}
    assert str(owned_wo.id) not in ids2          # no leak of srv's pushed WO
    # srv2 cannot act on srv's pushed task — foreign → 404 (no oracle).
    rx = await client.post(f"/api/servicer/tasks/{owned_wo.id}/accept")
    assert rx.status_code == 404, rx.text
    # srv2 owns bc_wo (accountable) but it sits in srv's section, NOT srv2's
    # claim zone — srv2 claiming it → 403 (zone gate, no leak/escalation).
    rxc = await client.post(f"/api/servicer/tasks/{bc_wo.id}/claim")
    assert rxc.status_code == 403, rxc.text

    # ---- claim a broadcast WO → 200; owner UNCHANGED, assignee = caller --
    await login(srv.username, _PW)
    rc = await client.post(f"/api/servicer/tasks/{bc_wo.id}/claim")
    assert rc.status_code == 200, rc.text
    bc_wo_row = await db.get(WorkOrder, bc_wo.id)
    await db.refresh(bc_wo_row)
    assert str(bc_wo_row.assigned_servicer_id) == str(srv.id)
    # D12: accountable owner UNCHANGED across a claim.
    assert str(bc_wo_row.accountable_owner_id) == str(bc_original_owner)

    # ---- claim a non-claimable WO (already pushed/owned) → 409 -----------
    rnc = await client.post(f"/api/servicer/tasks/{owned_wo.id}/claim")
    assert rnc.status_code == 409, rnc.text

    # ---- illegal order: complete before accept → 409 --------------------
    rbad = await client.post(f"/api/servicer/tasks/{owned_wo.id}/complete",
                             json={})
    assert rbad.status_code == 409, rbad.text

    # ---- accept → start → complete{notes} happy walk → 200 each ---------
    ra = await client.post(f"/api/servicer/tasks/{owned_wo.id}/accept")
    assert ra.status_code == 200, ra.text
    assert (await db.get(WorkOrder, owned_wo.id)).state == "accepted"
    # accept cancels the accept_window timer (C4 hop, D23).
    await db.refresh(owned_child)
    aw = (await db.execute(sa.select(Timer).where(
        Timer.child_id == owned_child.id,
        Timer.type == "accept_window"))).scalar_one()
    assert aw.state == "cancelled"

    rst = await client.post(f"/api/servicer/tasks/{owned_wo.id}/start")
    assert rst.status_code == 200, rst.text
    assert (await db.get(WorkOrder, owned_wo.id)).state == "in_progress"

    rcomp = await client.post(f"/api/servicer/tasks/{owned_wo.id}/complete",
                              json={"notes": "left fresh towels"})
    assert rcomp.status_code == 200, rcomp.text
    wo_done = await db.get(WorkOrder, owned_wo.id)
    assert wo_done.state == "completed"
    assert wo_done.completion_notes == "left fresh towels"
    # The C4 WO→completed hop fired: child → done_pending_confirm.
    assert (await db.get(ChildSubRequest, owned_child.id)).state == \
        "done_pending_confirm"

    # ---- raise {reason} → 201, spine-opened servicer_raised escalation ---
    rr = await client.post(f"/api/servicer/tasks/{bc_wo.id}/raise",
                           json={"reason": "guest not in room, blocked"})
    assert rr.status_code == 201, rr.text
    esc = (await db.execute(sa.select(Escalation).where(
        Escalation.child_id == bc_child.id))).scalar_one()
    assert esc.trigger == "servicer_raised"
    assert esc.state == "open"
    # Its recommendation + supervisor_sla timer exist (spine, not reinvented).
    rec = (await db.execute(sa.select(Recommendation).where(
        Recommendation.escalation_id == esc.id))).scalar_one()
    assert rec.action is not None
    sup_t = (await db.execute(sa.select(Timer).where(
        Timer.escalation_id == esc.id,
        Timer.type == "supervisor_sla"))).scalar_one()
    assert sup_t.state == "pending"

    # ---- foreign WO (random uuid) → 404 ----------------------------------
    r404 = await client.post(f"/api/servicer/tasks/{uuid.uuid4()}/accept")
    assert r404.status_code == 404, r404.text

    # ---- DELETE any task route → 405 -------------------------------------
    rd = await client.delete(f"/api/servicer/tasks/{owned_wo.id}/accept")
    assert rd.status_code == 405, rd.text
    rd2 = await client.delete("/api/servicer/tasks")
    assert rd2.status_code == 405, rd2.text
