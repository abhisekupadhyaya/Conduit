"""Task E1 — Guest dispatch status cards + confirm/reopen/cancel; intake→routing.

Spec §8 (Guest) + §9.2 (happy path). ONE full-ASGI scripted test driven over
the merged per-test ``client`` with a real per-role cookie chain (``login``
swaps the single active session cookie — the proven idiom in
``test_e2e_journey`` / ``test_e2e_staffing``). The dispatch classification is
made deterministic by the package ``fake_llm`` fixture (no network, no sleep).

The guest submits a dispatch-classifiable request through the MERGED intake
endpoint (NO new submit route): triage AUTO + ``fulfilment_mode == 'dispatch'``
must BRANCH to the C4 routing-effect (C1 ``routing.select`` → ``transition(...,
'routing', selection=...)`` creates the WorkOrder + arms accept_window +
fulfilment_sla). Then the four guest dispatch routes are exercised end to end
with the full status matrix (200 / 401 / 403 / 404 / 409 / 405).

Exact-count strategy under one savepoint: every assertion is scoped to the
freshly-returned identifiers (this request's child id / work order), so it is
robust regardless of prior rows within the single shared savepoint.
"""
from __future__ import annotations

import datetime as dt
import uuid

import sqlalchemy as sa

from conduit.shared.models import (
    Account,
    ChildSubRequest,
    EscalationLadder,
    Event,
    EventChildCancelled,
    Glitch,
    IssueCode,
    Property,
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

_PW = "pw-123456"  # conftest default in make_account / login


async def _seed_dispatch_world(db, make_account):
    """Full FK + routing + spine precondition.

    Property→Section→Room, an active P3 ``SLAPreset``, a dispatch
    ``IssueCode`` (``routing_model='section_pooled'``) pointing at it, an
    active ``EscalationLadder``, and a section-OWNER servicer that is
    ``effective_available`` now (active StaffProfile + a Roster window
    covering DB-now + an active owner RosterAssignment) so C1
    ``routing.select`` (section-pooled) yields a concrete assigned owner ⇒
    WorkOrder ``pushed``. Returns the guest account + the servicer +
    handles for assertions.
    """
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
                    accept_window_seconds=120,
                    fulfilment_sla_seconds=1800,
                    supervisor_sla_seconds=900, status="active")
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

    # Section owner servicer — effective_available now (D39).
    srv = await make_account("servicer", f"sv-{uuid.uuid4().hex[:8]}",
                             _PW, display_name="Sam Servicer")
    db.add(StaffProfile(account_id=srv.id, staff_class="housekeeping",
                        presence="working", status="active"))
    now = dt.datetime.now(dt.timezone.utc)
    roster = Roster(property_id=p.id,
                    shift_start=now - dt.timedelta(hours=1),
                    shift_end=now + dt.timedelta(hours=8), status="active")
    db.add(roster)
    await db.flush()
    db.add(RosterAssignment(roster_id=roster.id, account_id=srv.id,
                            section_id=sec.id, assignment="owner",
                            status="active"))
    await db.flush()

    # Guest with an active stay in that room.
    guest = await make_account("guest", f"g-{uuid.uuid4().hex[:8]}", _PW)
    stay = Stay(guest_account_id=guest.id, room_id=room.id,
                check_in=now, check_out=now + dt.timedelta(days=1),
                status="active")
    db.add(stay)
    await db.flush()
    return guest, srv, sec, ic


async def test_guest_dispatch_spine(client, make_account, login, db,
                                    fake_llm, fake_decompose):
    # Slice 7 makes intake multi-intent. This is a SINGLE-need dispatch
    # script (``scalar_one()`` on the one child / its one WorkOrder). The
    # ``fake_decompose`` double DEFAULTS to identity (1 message → 1 text —
    # ``state["texts"]`` unset), so the single utterance fans to exactly
    # one child and every ``scalar_one()`` stays unambiguous. No
    # behavioural assertion changes — only the single-intent assumption is
    # made explicit/deterministic.
    guest, srv, sec, ic = await _seed_dispatch_world(db, make_account)

    async def fclassify_dispatch(t, cat):
        return [{"text": t, "issue_code": "HK_TOWELS",
                 "fulfilment_mode": "dispatch", "outcome": "auto",
                 "is_problem_report": False}]

    fake_llm["classify"] = fclassify_dispatch

    # ---- No cookie → 401 -------------------------------------------------
    r = await client.get("/api/guest/requests")
    assert r.status_code == 401, r.text

    # ---- Submit via the MERGED intake endpoint (no new submit route) -----
    await login(guest.username, _PW)
    sub = await client.post("/api/guest/requests",
                            json={"text": "please send extra towels"})
    assert sub.status_code == 200, sub.text
    await db.flush()

    # A dispatch ChildSubRequest was created.
    child = (await db.execute(
        sa.select(ChildSubRequest)
        .where(ChildSubRequest.issue_code_id == ic.id)
    )).scalar_one()
    assert child.fulfilment_mode == "dispatch"
    assert child.outcome == "auto"
    # The routing-effect ran: a WorkOrder exists, pushed/broadcast, with the
    # accountable owner per D12 section-pooled routing.
    wo = (await db.execute(
        sa.select(WorkOrder).where(WorkOrder.child_id == child.id)
    )).scalar_one()
    assert wo.state in ("pushed", "broadcast")
    assert wo.kind == "dispatch"
    assert wo.routing_model == "section_pooled"
    # Owner available ⇒ pushed to the owner; owner is accountable (D12). The
    # dispatch leg's progress lives on the WorkOrder; the child sits at
    # ``routing`` (C4 models no child pushed/broadcast event).
    assert wo.state == "pushed"
    assert str(wo.assigned_servicer_id) == str(srv.id)
    assert str(wo.accountable_owner_id) == str(srv.id)
    assert child.state == "routing"
    # Both timers armed (D23) — accept_window + fulfilment_sla.
    timers = (await db.execute(
        sa.select(Timer).where(Timer.child_id == child.id,
                               Timer.state == "pending")
    )).scalars().all()
    assert {t.type for t in timers} == {"accept_window", "fulfilment_sla"}

    # ---- GET /api/guest/requests → 200, one dispatch card ----------------
    lst = await client.get("/api/guest/requests")
    assert lst.status_code == 200, lst.text
    cards = lst.json()
    card = next(c for c in cards if c["child_id"] == str(child.id))
    assert card["state"] == "pushed"
    assert card["issue_label"] == "Extra towels"
    assert card["assigned_servicer_name"] == "Sam Servicer"  # D17 NAME
    assert card["revised_eta"] is None
    assert card["glitch"] is False
    # No internal fields leak (extra="forbid" + curated keys only).
    assert set(card.keys()) == {
        "child_id", "state", "issue_label", "assigned_servicer_name",
        "revised_eta", "glitch"}

    # Glitch badge reflects an open Glitch for the child.
    db.add(Glitch(child_id=child.id, state="open",
                  opened_from="problem_report"))
    await db.flush()
    lst2 = await client.get("/api/guest/requests")
    card2 = next(c for c in lst2.json() if c["child_id"] == str(child.id))
    assert card2["glitch"] is True

    # ---- Wrong role (servicer cookie) → 403 ------------------------------
    await login(srv.username, _PW)
    rf = await client.get("/api/guest/requests")
    assert rf.status_code == 403, rf.text
    rfc = await client.post(f"/api/guest/requests/{child.id}/confirm")
    assert rfc.status_code == 403, rfc.text

    # ---- Foreign child (another guest) → 404 -----------------------------
    other = await make_account("guest", f"og-{uuid.uuid4().hex[:8]}", _PW)
    await login(other.username, _PW)
    rfor = await client.post(f"/api/guest/requests/{child.id}/confirm")
    assert rfor.status_code == 404, rfor.text
    rforc = await client.post(f"/api/guest/requests/{child.id}/cancel")
    assert rforc.status_code == 404, rforc.text

    # ---- Confirm on a non-pending child → 409 ----------------------------
    await login(guest.username, _PW)
    rbad = await client.post(f"/api/guest/requests/{child.id}/confirm")
    assert rbad.status_code == 409, rbad.text  # still 'pushed', not pending

    # ---- DELETE any of these routes → 405 --------------------------------
    rdel = await client.delete(f"/api/guest/requests/{child.id}/confirm")
    assert rdel.status_code == 405, rdel.text
    rdel2 = await client.delete("/api/guest/requests")
    assert rdel2.status_code == 405, rdel2.text

    # ---- Drive the child to done_pending_confirm via the REAL path -------
    # NO test-side model write of a journey transition. The child HOLDS at
    # its REAL state (``routing``, set by the real intake/routing-effect);
    # the WorkOrder carries the visible leg through the REAL C4 writer
    # (accepted→in_progress→completed). On WO → completed the §7.2 C4 hop
    # carries the routing-held child → done_pending_confirm (NOT conditional
    # on the child being in_progress — Spec §7.2).
    from conduit.shared.domain import lifecycle
    wo_row = await db.get(WorkOrder, wo.id)
    assert wo_row.state == "pushed"
    child_row = await db.get(ChildSubRequest, child.id)
    assert child_row.state == "routing"     # real holding state, untouched
    await lifecycle.transition(db, wo_row, "accepted",
                               actor_account_id=srv.id)
    await lifecycle.transition(db, wo_row, "in_progress",
                               actor_account_id=srv.id)
    await lifecycle.transition(db, wo_row, "completed",
                               actor_account_id=srv.id)
    await db.flush()
    child_row = await db.get(ChildSubRequest, child.id)
    assert child_row.state == "done_pending_confirm"
    await db.commit()

    # ---- POST confirm → 200, child closed --------------------------------
    rok = await client.post(f"/api/guest/requests/{child.id}/confirm")
    assert rok.status_code == 200, rok.text
    assert rok.json()["state"] == "closed"
    assert (await db.get(ChildSubRequest, child.id)).state == "closed"

    # ---- POST reopen → 200, child reopened (a fresh pending child) -------
    reopen_child = ChildSubRequest(
        request_id=child.request_id, text="x", outcome="auto",
        fulfilment_mode="dispatch", issue_code_id=ic.id,
        state="done_pending_confirm")
    db.add(reopen_child)
    await db.commit()
    rre = await client.post(f"/api/guest/requests/{reopen_child.id}/reopen")
    assert rre.status_code == 200, rre.text
    assert rre.json()["state"] == "reopened"
    assert (await db.get(ChildSubRequest, reopen_child.id)).state == "reopened"

    # ---- cancel AFTER closed → 409 ---------------------------------------
    # Take a fresh closed child to prove "already closed → 409".
    closed_child = ChildSubRequest(
        request_id=child.request_id, text="x", outcome="auto",
        fulfilment_mode="dispatch", issue_code_id=ic.id, state="closed")
    db.add(closed_child)
    await db.commit()
    rcl = await client.post(f"/api/guest/requests/{closed_child.id}/cancel")
    assert rcl.status_code == 409, rcl.text

    # ---- cancel BEFORE closed → 200 + the committed servicer notified ----
    pending = ChildSubRequest(
        request_id=child.request_id, text="x", outcome="auto",
        fulfilment_mode="dispatch", issue_code_id=ic.id,
        state="done_pending_confirm")
    db.add(pending)
    await db.commit()
    rcan = await client.post(f"/api/guest/requests/{pending.id}/cancel")
    assert rcan.status_code == 200, rcan.text
    assert (await db.get(ChildSubRequest, pending.id)).state == "cancelled"
    # The cancel notified the committed servicer: the C4 child_cancelled
    # append-only event IS the notification record (D37).
    cev = (await db.execute(
        sa.select(EventChildCancelled)
        .where(EventChildCancelled.child_id == pending.id)
    )).scalars().all()
    assert len(cev) == 1
    assert (await db.execute(sa.select(Event).where(
        Event.id == cev[0].event_id,
        Event.type == "child_cancelled"))).scalar_one()
