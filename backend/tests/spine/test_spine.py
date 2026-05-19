"""Spine tests — open_escalation (Spec §7.4, D9/D10/D20/D21).

DB-backed via the package ``db`` (savepoint-isolated) + ``make_child``. The
spine effects ONLY through the C4 ``lifecycle`` writer pattern and
``timers.arm``: an ``Escalation(open)`` linked to the child, a
``Recommendation`` + its matching ``rec_*`` detail row (the action chosen by
the PURE C2 ``recommendation.build``), exactly one ``escalation_opened`` and
one ``recommendation_created`` event (append-only), and a ``supervisor_sla``
``Timer`` whose ``fire_at`` is the DB ``now()`` plus the active
``SLAPreset.supervisor_sla_seconds`` for the child's tier (resolved via the
issue-code → SLAPreset chain, gated by the active ``EscalationLadder``).
"""
from __future__ import annotations

import datetime as dt
import uuid

import sqlalchemy as sa

from conduit.shared.engine.spine import (EscalationTrigger,
                                         apply_recommendation, hard_escalate,
                                         open_escalation)
from conduit.shared.models import (Account, Escalation, EscalationLadder,
                                   Event, EventEscalationOpened,
                                   EventEscalationResolved,
                                   EventRecommendationCreated, Glitch,
                                   IssueCode, Property, RecBroadcast,
                                   RecReassign, Recommendation, Request,
                                   Roster, RosterAssignment, Room, Section,
                                   SLAPreset, StaffProfile, Stay, Timer,
                                   WorkOrder)

SUPERVISOR_SLA_SECONDS = 900  # seeded, P3 tier — asserted exactly (no magic).
ACCEPT_WINDOW_SECONDS = 120
FULFILMENT_SLA_SECONDS = 1800


async def _seed_child_with_chain(db, make_account, *, with_servicer: bool):
    """Build the real FK chain Property→Section→Room→Account→Stay→Request→
    Child, plus the resolution prerequisites: an IssueCode whose
    ``sla_preset_id`` points at an active P3 ``SLAPreset`` for the property,
    and an active ``EscalationLadder`` for that property. The child's
    ``priority_tier`` is P3 so the tier→preset chain resolves.

    When ``with_servicer`` an extra non-stalled servicer Account is seeded
    with an active StaffProfile + a Roster window covering DB-now and an
    active RosterAssignment, so the engine-local candidate read makes it
    ``effective_available`` and C1 ``routing.select`` (skill_matched) yields a
    single reassign target → the stall recommendation is ``reassign``.
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
                    accept_window_seconds=ACCEPT_WINDOW_SECONDS,
                    fulfilment_sla_seconds=FULFILMENT_SLA_SECONDS,
                    supervisor_sla_seconds=SUPERVISOR_SLA_SECONDS,
                    status="active")
    db.add(sla)
    await db.flush()
    ic = IssueCode(code=f"IC-{uuid.uuid4().hex[:6]}", label="L",
                   department="engineering", fulfilment_mode="dispatch",
                   routing_model="skill_matched", sla_preset_id=sla.id)
    db.add(ic)
    await db.flush()
    db.add(EscalationLadder(property_id=p.id,
                            duty_manager_account_id=duty.id,
                            n_cycle_bound=3, status="active"))
    await db.flush()

    guest = await make_account("guest", f"g-{uuid.uuid4().hex[:8]}")
    now = dt.datetime.now(dt.timezone.utc)
    stay = Stay(guest_account_id=guest.id, room_id=room.id,
                check_in=now, check_out=now + dt.timedelta(days=1),
                status="active")
    db.add(stay)
    await db.flush()
    r = Request(guest_account_id=guest.id, stay_id=stay.id, raw_text="x")
    db.add(r)
    await db.flush()
    from conduit.shared.models import ChildSubRequest
    child = ChildSubRequest(request_id=r.id, text="x", outcome="auto",
                            state="in_progress", issue_code_id=ic.id,
                            priority_tier="P3")
    db.add(child)
    await db.flush()

    servicer = None
    if with_servicer:
        servicer = await make_account("servicer",
                                      f"sv-{uuid.uuid4().hex[:8]}")
        db.add(StaffProfile(account_id=servicer.id,
                            staff_class="engineering",
                            presence="working", status="active"))
        roster = Roster(property_id=p.id,
                        shift_start=now - dt.timedelta(hours=1),
                        shift_end=now + dt.timedelta(hours=8),
                        status="active")
        db.add(roster)
        await db.flush()
        db.add(RosterAssignment(roster_id=roster.id,
                                account_id=servicer.id,
                                assignment="member", status="active"))
        await db.flush()

    return child, p, sla, servicer


async def test_open_escalation_stall_full(db, make_child, make_account):
    child, prop, sla, servicer = await _seed_child_with_chain(
        db, make_account, with_servicer=True)

    db_now = (await db.execute(sa.select(sa.func.now()))).scalar_one()
    await open_escalation(db, child, EscalationTrigger.STALL,
                          stalled_account_id=uuid.uuid4())
    await db.flush()

    # --- Escalation(open) linked to the child, correct trigger -------------
    esc = (await db.execute(
        sa.select(Escalation).where(Escalation.child_id == child.id)
    )).scalars().all()
    assert len(esc) == 1
    esc = esc[0]
    assert esc.state == "open"
    assert esc.trigger == "stall"

    # --- Recommendation + the RIGHT per-action detail (stall→reassign) -----
    rec = (await db.execute(
        sa.select(Recommendation)
        .where(Recommendation.escalation_id == esc.id)
    )).scalar_one()
    assert rec.action == "reassign"
    assert rec.rationale_text
    reassign = (await db.execute(
        sa.select(RecReassign)
        .where(RecReassign.recommendation_escalation_id == esc.id)
    )).scalar_one()
    assert reassign.target_account_id == servicer.id
    # The non-chosen detail tables stay empty (exactly one detail row).
    assert (await db.execute(sa.select(RecBroadcast))).scalars().all() == []

    # --- exactly ONE escalation_opened AND ONE recommendation_created ------
    opened = (await db.execute(
        sa.select(Event).where(Event.type == "escalation_opened")
    )).scalars().all()
    assert len(opened) == 1
    opened_det = (await db.execute(
        sa.select(EventEscalationOpened)
        .where(EventEscalationOpened.escalation_id == esc.id)
    )).scalars().all()
    assert len(opened_det) == 1
    created = (await db.execute(
        sa.select(Event).where(Event.type == "recommendation_created")
    )).scalars().all()
    assert len(created) == 1
    created_det = (await db.execute(
        sa.select(EventRecommendationCreated)
        .where(EventRecommendationCreated.recommendation_escalation_id
               == esc.id)
    )).scalars().all()
    assert len(created_det) == 1

    # --- supervisor_sla Timer: pending, escalation-scoped, fire_at exact ---
    timers = (await db.execute(
        sa.select(Timer).where(Timer.escalation_id == esc.id)
    )).scalars().all()
    assert len(timers) == 1
    t = timers[0]
    assert t.type == "supervisor_sla"
    assert t.state == "pending"
    assert t.escalation_id == esc.id
    # fire_at == DB now() + the SEEDED active SLAPreset(P3) supervisor SLA.
    expected = db_now + dt.timedelta(seconds=sla.supervisor_sla_seconds)
    assert abs((t.fire_at - expected).total_seconds()) < 2.0


async def test_open_escalation_servicer_raised_extends_sla(db, make_child,
                                                           make_account):
    # No deterministic available room is wired → recommendation.build for
    # servicer_raised falls to extend_sla. Asserts the spine still opens the
    # escalation, persists the matching detail, and arms the timer.
    child, prop, sla, _ = await _seed_child_with_chain(
        db, make_account, with_servicer=False)
    await open_escalation(db, child, EscalationTrigger.SERVICER_RAISED)
    await db.flush()

    esc = (await db.execute(
        sa.select(Escalation).where(Escalation.child_id == child.id)
    )).scalar_one()
    assert esc.state == "open" and esc.trigger == "servicer_raised"
    rec = (await db.execute(
        sa.select(Recommendation)
        .where(Recommendation.escalation_id == esc.id)
    )).scalar_one()
    assert rec.action == "extend_sla"
    from conduit.shared.models import RecExtendSla
    det = (await db.execute(
        sa.select(RecExtendSla)
        .where(RecExtendSla.recommendation_escalation_id == esc.id)
    )).scalar_one()
    assert det.extend_seconds == sla.fulfilment_sla_seconds
    assert len((await db.execute(
        sa.select(Event).where(Event.type == "escalation_opened")
    )).scalars().all()) == 1
    assert len((await db.execute(
        sa.select(Timer).where(Timer.escalation_id == esc.id)
    )).scalars().all()) == 1


async def test_open_escalation_triage_flag_denies(db, make_child,
                                                  make_account):
    child, prop, sla, _ = await _seed_child_with_chain(
        db, make_account, with_servicer=False)
    await open_escalation(db, child, EscalationTrigger.TRIAGE_FLAG,
                          verdict="deny")
    await db.flush()

    esc = (await db.execute(
        sa.select(Escalation).where(Escalation.child_id == child.id)
    )).scalar_one()
    assert esc.state == "open" and esc.trigger == "triage_flag"
    rec = (await db.execute(
        sa.select(Recommendation)
        .where(Recommendation.escalation_id == esc.id)
    )).scalar_one()
    assert rec.action == "deny"
    from conduit.shared.models import RecDeny
    assert (await db.execute(
        sa.select(RecDeny)
        .where(RecDeny.recommendation_escalation_id == esc.id)
    )).scalar_one() is not None
    assert len((await db.execute(
        sa.select(Event).where(Event.type == "recommendation_created")
    )).scalars().all()) == 1


# ===========================================================================
# Task D2 — apply_recommendation single executor + D21 bounded hard_escalate
# ===========================================================================


async def _seed_stall_scenario(db, make_account, *, routing_model="skill_matched",
                                n_cycle_bound=3, cycle_count=0):
    """Full FK chain + a routed WorkOrder + an open stall Escalation with a
    stored ``reassign`` Recommendation pointing at a fresh non-stalled
    servicer that C1 ``routing.select`` will pick.

    The WorkOrder's accountable owner is a DISTINCT account (the section
    owner) so the "owner UNCHANGED" invariant is observable. Returns a dict
    of the seeded handles.
    """
    duty = await make_account("supervisor", f"dm-{uuid.uuid4().hex[:8]}")
    owner = await make_account("servicer", f"ow-{uuid.uuid4().hex[:8]}")
    stalled = await make_account("servicer", f"st-{uuid.uuid4().hex[:8]}")
    target = await make_account("servicer", f"tg-{uuid.uuid4().hex[:8]}")

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
                    accept_window_seconds=ACCEPT_WINDOW_SECONDS,
                    fulfilment_sla_seconds=FULFILMENT_SLA_SECONDS,
                    supervisor_sla_seconds=SUPERVISOR_SLA_SECONDS,
                    status="active")
    db.add(sla)
    await db.flush()
    ic = IssueCode(code=f"IC-{uuid.uuid4().hex[:6]}", label="L",
                   department="engineering", fulfilment_mode="dispatch",
                   routing_model=routing_model, sla_preset_id=sla.id)
    db.add(ic)
    await db.flush()
    db.add(EscalationLadder(property_id=p.id,
                            duty_manager_account_id=duty.id,
                            n_cycle_bound=n_cycle_bound, status="active"))
    await db.flush()

    guest = await make_account("guest", f"g-{uuid.uuid4().hex[:8]}")
    now = dt.datetime.now(dt.timezone.utc)
    stay = Stay(guest_account_id=guest.id, room_id=room.id,
                check_in=now, check_out=now + dt.timedelta(days=1),
                status="active")
    db.add(stay)
    await db.flush()
    r = Request(guest_account_id=guest.id, stay_id=stay.id, raw_text="x")
    db.add(r)
    await db.flush()
    from conduit.shared.models import ChildSubRequest
    child = ChildSubRequest(request_id=r.id, text="x", outcome="auto",
                            state="in_progress", issue_code_id=ic.id,
                            priority_tier="P3")
    db.add(child)
    await db.flush()

    wo = WorkOrder(child_id=child.id, kind="dispatch",
                   routing_model=routing_model, priority_tier="P3",
                   assigned_servicer_id=stalled.id,
                   accountable_owner_id=owner.id,
                   section_id=sec.id, state="created")
    db.add(wo)
    await db.flush()

    # The fresh non-stalled servicer C1 routing.select will pick.
    db.add(StaffProfile(account_id=target.id, staff_class="engineering",
                        presence="working", status="active"))
    roster = Roster(property_id=p.id,
                    shift_start=now - dt.timedelta(hours=1),
                    shift_end=now + dt.timedelta(hours=8),
                    status="active")
    db.add(roster)
    await db.flush()
    db.add(RosterAssignment(roster_id=roster.id, account_id=target.id,
                            assignment="member", status="active"))
    await db.flush()

    esc = Escalation(child_id=child.id, trigger="stall", state="open",
                     cycle_count=cycle_count, raised_by_account_id=None)
    db.add(esc)
    await db.flush()
    db.add(Recommendation(escalation_id=esc.id, action="reassign",
                          rationale_text="reassign to the routed target"))
    await db.flush()
    db.add(RecReassign(recommendation_escalation_id=esc.id,
                       target_account_id=target.id))
    await db.flush()

    return {"child": child, "prop": p, "sla": sla, "wo": wo, "esc": esc,
            "owner": owner, "stalled": stalled, "target": target,
            "section": sec, "stay": stay, "room": room, "duty": duty}


async def test_apply_recommendation_approved_stall_reassign(db, make_account):
    """(a) approved stall+reassign: WO assignee → routing target, owner
    UNCHANGED, escalation resolved (approved) with resolver+timestamp, exactly
    one escalation_resolved event."""
    h = await _seed_stall_scenario(db, make_account)
    actor = await make_account("supervisor", f"sup-{uuid.uuid4().hex[:8]}")

    await apply_recommendation(db, h["esc"], outcome="approved",
                               actor=actor.id)
    await db.flush()

    wo = (await db.execute(
        sa.select(WorkOrder).where(WorkOrder.id == h["wo"].id)
    )).scalar_one()
    assert wo.assigned_servicer_id == h["target"].id
    assert wo.accountable_owner_id == h["owner"].id  # UNCHANGED

    esc = (await db.execute(
        sa.select(Escalation).where(Escalation.id == h["esc"].id)
    )).scalar_one()
    assert esc.state == "approved"
    assert esc.resolved_by_account_id == actor.id
    assert esc.resolved_at is not None

    resolved = (await db.execute(
        sa.select(EventEscalationResolved)
        .where(EventEscalationResolved.escalation_id == esc.id)
    )).scalars().all()
    assert len(resolved) == 1


async def test_apply_recommendation_symmetry_approved_vs_auto(db, make_account):
    """(b) approved vs auto_proceeded produce IDENTICAL post-state EXCEPT
    escalation.state and resolved_by_account_id. Explicit symmetry diff."""
    ha = await _seed_stall_scenario(db, make_account)
    hb = await _seed_stall_scenario(db, make_account)
    actor = await make_account("supervisor", f"sup-{uuid.uuid4().hex[:8]}")

    await apply_recommendation(db, ha["esc"], outcome="approved",
                               actor=actor.id)
    await apply_recommendation(db, hb["esc"], outcome="auto_proceeded")
    await db.flush()

    wa = (await db.execute(
        sa.select(WorkOrder).where(WorkOrder.id == ha["wo"].id))).scalar_one()
    wb = (await db.execute(
        sa.select(WorkOrder).where(WorkOrder.id == hb["wo"].id))).scalar_one()
    # Identical WO effect: same assignee target, same (unchanged) owner.
    assert wa.assigned_servicer_id == ha["target"].id
    assert wb.assigned_servicer_id == hb["target"].id
    assert wa.accountable_owner_id == ha["owner"].id
    assert wb.accountable_owner_id == hb["owner"].id

    ea = (await db.execute(
        sa.select(Escalation).where(Escalation.id == ha["esc"].id)
    )).scalar_one()
    eb = (await db.execute(
        sa.select(Escalation).where(Escalation.id == hb["esc"].id)
    )).scalar_one()
    # Identical child state.
    ca = (await db.execute(
        sa.select(type(ha["child"]))
        .where(type(ha["child"]).id == ha["child"].id))).scalar_one()
    cb = (await db.execute(
        sa.select(type(hb["child"]))
        .where(type(hb["child"]).id == hb["child"].id))).scalar_one()
    assert ca.state == cb.state
    # Identical cycle bump.
    assert ea.cycle_count == eb.cycle_count == 1
    # Exactly one escalation_resolved per resolution.
    ra = (await db.execute(sa.select(EventEscalationResolved)
          .where(EventEscalationResolved.escalation_id == ea.id)
          )).scalars().all()
    rb = (await db.execute(sa.select(EventEscalationResolved)
          .where(EventEscalationResolved.escalation_id == eb.id)
          )).scalars().all()
    assert len(ra) == 1 and len(rb) == 1
    # The ONLY differences: state + resolved_by.
    assert ea.state == "approved" and eb.state == "auto_proceeded"
    assert ea.resolved_by_account_id == actor.id
    assert eb.resolved_by_account_id is None
    # Everything else symmetric.
    assert ea.trigger == eb.trigger
    assert ea.resolved_at is not None and eb.resolved_at is not None


async def test_apply_recommendation_extend_sla_rearms_timer(db, make_account):
    """(c) extend_sla outcome re-arms a pending fulfilment/supervisor timer
    with the recommended extend_seconds."""
    h = await _seed_stall_scenario(db, make_account)
    esc = h["esc"]
    # Replace the stored rec with extend_sla.
    await db.execute(sa.delete(RecReassign).where(
        RecReassign.recommendation_escalation_id == esc.id))
    await db.execute(sa.update(Recommendation).where(
        Recommendation.escalation_id == esc.id).values(action="extend_sla"))
    from conduit.shared.models import RecExtendSla
    db.add(RecExtendSla(recommendation_escalation_id=esc.id,
                        extend_seconds=4242))
    await db.flush()
    db_now = (await db.execute(sa.select(sa.func.now()))).scalar_one()

    await apply_recommendation(db, esc, outcome="approved",
                               actor=h["duty"].id)
    await db.flush()

    timers = (await db.execute(
        sa.select(Timer).where(Timer.escalation_id == esc.id,
                               Timer.state == "pending")
    )).scalars().all()
    assert len(timers) == 1
    t = timers[0]
    assert t.type in ("supervisor_sla", "fulfilment_sla")
    expected = db_now + dt.timedelta(seconds=4242)
    assert abs((t.fire_at - expected).total_seconds()) < 2.0


async def test_apply_recommendation_relocate_closes_glitch(db, make_account):
    """(c) relocate outcome calls the merged relocate_stay seam + transitions
    the linked Glitch closed."""
    h = await _seed_stall_scenario(db, make_account)
    esc = h["esc"]
    # The system FO-GUEST-MOVE issue code (B1 seeds it in the real catalog;
    # the spine bench builds a minimal chain so seed it here) — the relocate
    # resolution additionally spawns the front-office move task (spec §7.3).
    await _seed_fo_guest_move_code(db)
    # New room to relocate into.
    new_room = Room(section_id=h["section"].id, label="R2")
    db.add(new_room)
    await db.flush()
    await db.execute(sa.delete(RecReassign).where(
        RecReassign.recommendation_escalation_id == esc.id))
    await db.execute(sa.update(Recommendation).where(
        Recommendation.escalation_id == esc.id).values(action="relocate"))
    from conduit.shared.models import RecRelocate
    db.add(RecRelocate(recommendation_escalation_id=esc.id,
                       target_room_id=new_room.id))
    glitch = Glitch(child_id=h["child"].id, state="open",
                    opened_from="problem_report")
    db.add(glitch)
    await db.flush()

    await apply_recommendation(db, esc, outcome="approved",
                               actor=h["duty"].id,
                               stay_id=h["stay"].id,
                               new_room_id=new_room.id)
    await db.flush()

    st = (await db.execute(
        sa.select(Stay).where(Stay.id == h["stay"].id))).scalar_one()
    assert st.room_id == new_room.id  # real relocate_stay ran
    gl = (await db.execute(
        sa.select(Glitch).where(Glitch.id == glitch.id))).scalar_one()
    assert gl.state in ("closed", "auto_closed")
    esc_row = (await db.execute(
        sa.select(Escalation).where(Escalation.id == esc.id))).scalar_one()
    assert esc_row.state == "approved"


async def test_apply_recommendation_d21_bound_hard_escalates(db, make_account):
    """(d) cycle_count+1 >= n_cycle_bound + auto_proceeded → hard_escalate
    INSTEAD: state hard_escalated, NO reassign executed, one event, no
    out-of-band side effect."""
    h = await _seed_stall_scenario(db, make_account, n_cycle_bound=3,
                                   cycle_count=2)
    esc = h["esc"]

    await apply_recommendation(db, esc, outcome="auto_proceeded")
    await db.flush()

    esc_row = (await db.execute(
        sa.select(Escalation).where(Escalation.id == esc.id))).scalar_one()
    assert esc_row.state == "hard_escalated"
    assert esc_row.resolved_by_account_id is None
    # NO reassign action executed — WO assignee stays the stalled servicer.
    wo = (await db.execute(
        sa.select(WorkOrder).where(WorkOrder.id == h["wo"].id))).scalar_one()
    assert wo.assigned_servicer_id == h["stalled"].id
    # Exactly one escalation_resolved event (the hard_escalate disposition).
    resolved = (await db.execute(
        sa.select(EventEscalationResolved)
        .where(EventEscalationResolved.escalation_id == esc.id)
    )).scalars().all()
    assert len(resolved) == 1
    # No out-of-band side effect: no timers armed by the action path.
    timers = (await db.execute(
        sa.select(Timer).where(Timer.escalation_id == esc.id)
    )).scalars().all()
    assert timers == []


async def test_hard_escalate_direct(db, make_account):
    """hard_escalate(s, escalation): state hard_escalated, one event, no
    action effect, no out-of-band."""
    h = await _seed_stall_scenario(db, make_account)
    esc = h["esc"]
    await hard_escalate(db, esc)
    await db.flush()
    esc_row = (await db.execute(
        sa.select(Escalation).where(Escalation.id == esc.id))).scalar_one()
    assert esc_row.state == "hard_escalated"
    wo = (await db.execute(
        sa.select(WorkOrder).where(WorkOrder.id == h["wo"].id))).scalar_one()
    assert wo.assigned_servicer_id == h["stalled"].id
    resolved = (await db.execute(
        sa.select(EventEscalationResolved)
        .where(EventEscalationResolved.escalation_id == esc.id)
    )).scalars().all()
    assert len(resolved) == 1


async def test_apply_recommendation_edited_uses_supplied_action(db,
                                                                make_account):
    """edited/overridden carry a supervisor-supplied action; it executes the
    SUPPLIED action, not the stored reassign rec."""
    h = await _seed_stall_scenario(db, make_account)
    esc = h["esc"]
    other = await make_account("servicer", f"ot-{uuid.uuid4().hex[:8]}")

    # Supervisor edits: reassign to `other` (NOT the stored target).
    await apply_recommendation(db, esc, outcome="edited", actor=h["duty"].id,
                               action="reassign",
                               payload={"target_account_id": other.id})
    await db.flush()

    wo = (await db.execute(
        sa.select(WorkOrder).where(WorkOrder.id == h["wo"].id))).scalar_one()
    assert wo.assigned_servicer_id == other.id  # supplied, not stored target
    assert wo.assigned_servicer_id != h["target"].id
    esc_row = (await db.execute(
        sa.select(Escalation).where(Escalation.id == esc.id))).scalar_one()
    assert esc_row.state == "edited"
    assert esc_row.resolved_by_account_id == h["duty"].id


async def test_d1_fix_section_pooled_stall_routes_via_d12(db, make_account):
    """(e) Folded-in D1 fix: a section_pooled child's STALL recommendation
    routes via the D12 section-pooled model — a claim-fallback BROADCAST to
    the in-zone available pool — NOT the hardcoded skill_matched model.

    Under D18 skill_matched the same single available engineer would be the
    sole reassign target (action='reassign'). Under D12 section_pooled with
    no positional owner among candidates, routing.select returns a
    broadcast_pool → recommendation.build yields action='broadcast'. The
    broadcast outcome is therefore proof the model was DERIVED from
    issue_code.routing_model ('section_pooled'), not hardcoded skill.
    """
    duty = await make_account("supervisor", f"dm-{uuid.uuid4().hex[:8]}")
    owner = await make_account("servicer", f"ow-{uuid.uuid4().hex[:8]}")
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
                    accept_window_seconds=ACCEPT_WINDOW_SECONDS,
                    fulfilment_sla_seconds=FULFILMENT_SLA_SECONDS,
                    supervisor_sla_seconds=SUPERVISOR_SLA_SECONDS,
                    status="active")
    db.add(sla)
    await db.flush()
    ic = IssueCode(code=f"IC-{uuid.uuid4().hex[:6]}", label="L",
                   department="housekeeping", fulfilment_mode="dispatch",
                   routing_model="section_pooled", sla_preset_id=sla.id)
    db.add(ic)
    await db.flush()
    db.add(EscalationLadder(property_id=p.id,
                            duty_manager_account_id=duty.id,
                            n_cycle_bound=3, status="active"))
    await db.flush()

    guest = await make_account("guest", f"g-{uuid.uuid4().hex[:8]}")
    now = dt.datetime.now(dt.timezone.utc)
    stay = Stay(guest_account_id=guest.id, room_id=room.id,
                check_in=now, check_out=now + dt.timedelta(days=1),
                status="active")
    db.add(stay)
    await db.flush()
    r = Request(guest_account_id=guest.id, stay_id=stay.id, raw_text="x")
    db.add(r)
    await db.flush()
    from conduit.shared.models import ChildSubRequest
    child = ChildSubRequest(request_id=r.id, text="x", outcome="auto",
                            state="in_progress", issue_code_id=ic.id,
                            priority_tier="P3")
    db.add(child)
    await db.flush()

    # One available in-zone servicer, NOT a positional owner. Under D18
    # skill_matched it would be the sole reassign target; under D12
    # section_pooled (no owner among candidates) it goes to the
    # claim-fallback broadcast pool instead.
    db.add(StaffProfile(account_id=owner.id, staff_class="housekeeping",
                        presence="working", status="active"))
    roster = Roster(property_id=p.id,
                    shift_start=now - dt.timedelta(hours=1),
                    shift_end=now + dt.timedelta(hours=8),
                    status="active")
    db.add(roster)
    await db.flush()
    db.add(RosterAssignment(roster_id=roster.id, account_id=owner.id,
                            assignment="member", status="active"))
    await db.flush()

    await open_escalation(db, child, EscalationTrigger.STALL,
                          stalled_account_id=uuid.uuid4())
    await db.flush()

    esc = (await db.execute(
        sa.select(Escalation).where(Escalation.child_id == child.id)
    )).scalar_one()
    rec = (await db.execute(
        sa.select(Recommendation)
        .where(Recommendation.escalation_id == esc.id))).scalar_one()
    # D12 section-pooled produced a broadcast (no positional owner ⇒
    # claim-fallback). Proves the routing model was DERIVED from
    # issue_code.routing_model ('section_pooled'), not hardcoded skill
    # (which would have yielded action='reassign' to the lone engineer).
    assert rec.action == "broadcast"
    det = (await db.execute(
        sa.select(RecBroadcast)
        .where(RecBroadcast.recommendation_escalation_id == esc.id)
    )).scalar_one()
    assert det is not None


# ===========================================================================
# Task B4 — servicer_raised relocate: compute + persist the room at build,
# auto-proceed-safe (spec §7.2 / §4 "Auto-proceed safety"; D9/D30).
# ===========================================================================


async def _seed_servicer_raised_relocate(db, make_account, *,
                                          n_eligible_rooms: int):
    """Real FK chain Property→Section→Room(s)→Account→Stay→Request→Child for
    a SERVICER_RAISED escalation, plus the SLAPreset/IssueCode/EscalationLadder
    prerequisites and a linked open Glitch (the recovery a relocate
    discharges).

    The guest's Stay sits in ``current_room``. ``n_eligible_rooms`` extra
    vacant rooms are created in the SAME section (no active Stay → eligible);
    ``occupied_room`` always holds another active Stay so occupancy exclusion
    is observable. With ``n_eligible_rooms == 0`` no room is eligible →
    ``room_selection`` returns ``None`` → ``recommendation.build`` falls back
    to ``extend_sla`` (the inherited regression).

    ``rooms`` are returned in creation order; ``room_selection`` preserves the
    caller (engine) order, so the FIRST eligible room is the deterministic
    pick.
    """
    duty = await make_account("supervisor", f"dm-{uuid.uuid4().hex[:8]}")
    p = Property(name="T")
    db.add(p)
    await db.flush()
    sec = Section(property_id=p.id, label="S")
    db.add(sec)
    await db.flush()

    current_room = Room(section_id=sec.id, label="cur")
    db.add(current_room)
    await db.flush()
    occupied_room = Room(section_id=sec.id, label="occ")
    db.add(occupied_room)
    await db.flush()
    eligible_rooms = []
    for i in range(n_eligible_rooms):
        rm = Room(section_id=sec.id, label=f"elig-{i}")
        db.add(rm)
        await db.flush()
        eligible_rooms.append(rm)

    sla = SLAPreset(property_id=p.id, tier="P3",
                    accept_window_seconds=ACCEPT_WINDOW_SECONDS,
                    fulfilment_sla_seconds=FULFILMENT_SLA_SECONDS,
                    supervisor_sla_seconds=SUPERVISOR_SLA_SECONDS,
                    status="active")
    db.add(sla)
    await db.flush()
    ic = IssueCode(code=f"IC-{uuid.uuid4().hex[:6]}", label="L",
                   department="engineering", fulfilment_mode="dispatch",
                   routing_model="skill_matched", sla_preset_id=sla.id)
    db.add(ic)
    await db.flush()
    db.add(EscalationLadder(property_id=p.id,
                            duty_manager_account_id=duty.id,
                            n_cycle_bound=3, status="active"))
    await db.flush()

    now = dt.datetime.now(dt.timezone.utc)
    guest = await make_account("guest", f"g-{uuid.uuid4().hex[:8]}")
    stay = Stay(guest_account_id=guest.id, room_id=current_room.id,
                check_in=now, check_out=now + dt.timedelta(days=1),
                status="active")
    db.add(stay)
    await db.flush()
    # A DIFFERENT guest's active Stay occupies ``occupied_room`` so the
    # occupancy-exclusion path is exercised (it must NEVER be the pick).
    other_guest = await make_account("guest", f"og-{uuid.uuid4().hex[:8]}")
    db.add(Stay(guest_account_id=other_guest.id, room_id=occupied_room.id,
                check_in=now, check_out=now + dt.timedelta(days=1),
                status="active"))
    await db.flush()

    r = Request(guest_account_id=guest.id, stay_id=stay.id, raw_text="x")
    db.add(r)
    await db.flush()
    from conduit.shared.models import ChildSubRequest
    child = ChildSubRequest(request_id=r.id, text="x", outcome="auto",
                            state="in_progress", issue_code_id=ic.id,
                            priority_tier="P3")
    db.add(child)
    await db.flush()
    glitch = Glitch(child_id=child.id, state="open",
                    opened_from="problem_report")
    db.add(glitch)
    await db.flush()

    return {"child": child, "prop": p, "sla": sla, "section": sec,
            "stay": stay, "current_room": current_room,
            "occupied_room": occupied_room, "eligible_rooms": eligible_rooms,
            "glitch": glitch, "duty": duty}


async def test_open_escalation_servicer_raised_persists_computed_room(
        db, make_account):
    """§7.2: the SERVICER_RAISED branch does an ENGINE-LOCAL rooms/occupancy
    read and feeds room_selection; the recommendation is ``relocate`` with the
    DETERMINISTIC pick PERSISTED on ``RecRelocate.target_room_id`` — NOT a
    ``ctx.get`` passthrough and NOT the occupied/current room."""
    h = await _seed_servicer_raised_relocate(db, make_account,
                                             n_eligible_rooms=2)

    # No available_room_id supplied via ctx — proves the spine COMPUTES it.
    await open_escalation(db, h["child"], EscalationTrigger.SERVICER_RAISED)
    await db.flush()

    esc = (await db.execute(
        sa.select(Escalation).where(Escalation.child_id == h["child"].id)
    )).scalar_one()
    assert esc.state == "open" and esc.trigger == "servicer_raised"
    rec = (await db.execute(
        sa.select(Recommendation)
        .where(Recommendation.escalation_id == esc.id))).scalar_one()
    assert rec.action == "relocate"
    from conduit.shared.models import RecRelocate
    det = (await db.execute(
        sa.select(RecRelocate)
        .where(RecRelocate.recommendation_escalation_id == esc.id)
    )).scalar_one()
    # Deterministic: the FIRST eligible room (creation/engine order), never
    # the guest's current room nor the occupied room.
    assert det.target_room_id == h["eligible_rooms"][0].id
    assert det.target_room_id != h["current_room"].id
    assert det.target_room_id != h["occupied_room"].id


async def test_open_escalation_servicer_raised_no_eligible_room_extends_sla(
        db, make_account):
    """Regression preserved: zero eligible rooms ⇒ room_selection → None ⇒
    recommendation.build falls back to ``extend_sla`` (verbatim)."""
    h = await _seed_servicer_raised_relocate(db, make_account,
                                             n_eligible_rooms=0)
    await open_escalation(db, h["child"], EscalationTrigger.SERVICER_RAISED)
    await db.flush()

    esc = (await db.execute(
        sa.select(Escalation).where(Escalation.child_id == h["child"].id)
    )).scalar_one()
    rec = (await db.execute(
        sa.select(Recommendation)
        .where(Recommendation.escalation_id == esc.id))).scalar_one()
    assert rec.action == "extend_sla"
    from conduit.shared.models import RecExtendSla
    det = (await db.execute(
        sa.select(RecExtendSla)
        .where(RecExtendSla.recommendation_escalation_id == esc.id)
    )).scalar_one()
    assert det.extend_seconds == h["sla"].fulfilment_sla_seconds


async def test_servicer_raised_relocate_auto_proceed_equals_approve(
        db, make_account):
    """THE signature test (§7.2 / §4 "Auto-proceed safety"; D9/D30).

    A SERVICER_RAISED relocate resolved by SILENCE/auto-proceed (the
    supervisor-SLA-breach ``runner.tick`` path — NO ctx supplied) reaches an
    end-state IDENTICAL to the ``approve`` path, in EVERY field except
    ``resolved_by_account_id`` (set for approve, ``None`` for auto-proceed).
    The auto-proceed path re-applies the PERSISTED
    ``RecRelocate.target_room_id`` — selection never re-runs.
    """
    from conduit.shared.engine import runner

    # The system FO-GUEST-MOVE code (B1 seeds it in the real catalog; the
    # spine bench builds a minimal chain so seed it here) — relocate
    # resolution additionally spawns the front-office move task (spec §7.3).
    await _seed_fo_guest_move_code(db)

    # --- Path A: explicit human approve --------------------------------------
    ha = await _seed_servicer_raised_relocate(db, make_account,
                                              n_eligible_rooms=1)
    actor = await make_account("supervisor", f"sup-{uuid.uuid4().hex[:8]}")
    await open_escalation(db, ha["child"], EscalationTrigger.SERVICER_RAISED)
    await db.flush()
    esc_a = (await db.execute(
        sa.select(Escalation).where(Escalation.child_id == ha["child"].id)
    )).scalar_one()
    from conduit.shared.models import RecRelocate
    persisted_a = (await db.execute(
        sa.select(RecRelocate.target_room_id)
        .where(RecRelocate.recommendation_escalation_id == esc_a.id)
    )).scalar_one()
    assert persisted_a == ha["eligible_rooms"][0].id
    # Approve supplies NO stay_id/new_room_id ctx — the spine resolves them
    # from the persisted room + child→Request→Stay (identical to silence).
    await apply_recommendation(db, esc_a, outcome="approved", actor=actor.id)
    await db.flush()

    # --- Path B: silent auto-proceed via the real SLA-breach runner.tick -----
    hb = await _seed_servicer_raised_relocate(db, make_account,
                                              n_eligible_rooms=1)
    await open_escalation(db, hb["child"], EscalationTrigger.SERVICER_RAISED)
    await db.flush()
    esc_b = (await db.execute(
        sa.select(Escalation).where(Escalation.child_id == hb["child"].id)
    )).scalar_one()
    persisted_b = (await db.execute(
        sa.select(RecRelocate.target_room_id)
        .where(RecRelocate.recommendation_escalation_id == esc_b.id)
    )).scalar_one()
    # Arm the supervisor_sla timer in the past → the next runner.tick
    # auto-proceeds through the REAL spine (no ctx supplied).
    db_now = (await db.execute(sa.select(sa.func.now()))).scalar_one()
    from conduit.shared.engine import timers as _t
    await _t.arm(db, "escalation_id", esc_b.id, _t.TimerType.SUPERVISOR_SLA,
                 fire_at=db_now - dt.timedelta(seconds=5))
    await db.flush()
    fired = await runner.tick(db)
    assert fired >= 1
    await db.flush()

    # --- The end-states must be IDENTICAL except resolved_by_account_id ------
    esc_a = (await db.execute(
        sa.select(Escalation).where(Escalation.id == esc_a.id))).scalar_one()
    esc_b = (await db.execute(
        sa.select(Escalation).where(Escalation.id == esc_b.id))).scalar_one()
    # The single structural difference: resolver set for approve, None for
    # the silence path (state differs only by the outcome label).
    assert esc_a.state == "approved"
    assert esc_b.state == "auto_proceeded"
    assert esc_a.resolved_by_account_id == actor.id
    assert esc_b.resolved_by_account_id is None
    assert esc_a.resolved_at is not None and esc_b.resolved_at is not None
    assert esc_a.cycle_count == esc_b.cycle_count  # both +1

    # The REAL relocate_stay re-bind ran on BOTH paths using the PERSISTED
    # room (selection never re-ran in the auto-proceed path).
    st_a = (await db.execute(
        sa.select(Stay).where(Stay.id == ha["stay"].id))).scalar_one()
    st_b = (await db.execute(
        sa.select(Stay).where(Stay.id == hb["stay"].id))).scalar_one()
    assert st_a.room_id == persisted_a == ha["eligible_rooms"][0].id
    assert st_b.room_id == persisted_b == hb["eligible_rooms"][0].id

    # The linked Glitch closed on BOTH paths (identical recovery effect).
    gl_a = (await db.execute(
        sa.select(Glitch).where(Glitch.id == ha["glitch"].id))).scalar_one()
    gl_b = (await db.execute(
        sa.select(Glitch).where(Glitch.id == hb["glitch"].id))).scalar_one()
    assert gl_a.state in ("closed", "auto_closed")
    assert gl_b.state in ("closed", "auto_closed")

    # Exactly one escalation_resolved event on EACH (append-only symmetry).
    for e in (esc_a, esc_b):
        rs = (await db.execute(
            sa.select(EventEscalationResolved)
            .where(EventEscalationResolved.escalation_id == e.id)
        )).scalars().all()
        assert len(rs) == 1


# ===========================================================================
# Task B5 — spawn the front-office "guest move" task on relocate execution
# (spec §7.3 / §4 decisions 5a & 2). One ChildSubRequest reusing the
# triggering child's Request (lineage via predecessor_child_id — its first
# real consumer) + one WorkOrder kind='relocation_move' routed via the
# EXISTING C4 routing path, visible on the existing servicer queue.
# ===========================================================================


async def _seed_fo_guest_move_code(db):
    """Get-or-create the system ``FO-GUEST-MOVE`` IssueCode (the exact spec
    shape: origin='system', dispatch, section_pooled).

    Idempotent: migration 0007 seeds it in the real catalog and the spine
    bench restores that canonical post-``upgrade head`` row after its
    one-shot leakage-reset truncate, so the row is normally already present.
    Re-inserting would violate the ``lower(code)`` unique index — so reuse
    the existing row when present, else create it (covers any ordering)."""
    existing = (await db.execute(sa.select(IssueCode).where(
        sa.func.lower(IssueCode.code) == "fo-guest-move"))).scalars().first()
    if existing is not None:
        return existing
    ic = IssueCode(code="FO-GUEST-MOVE", label="Guest move",
                   department="front_office", fulfilment_mode="dispatch",
                   routing_model="section_pooled", intent_kind="service",
                   is_reservation_mutation=False, origin="system",
                   status="active")
    db.add(ic)
    await db.flush()
    return ic


async def test_apply_recommendation_relocate_spawns_move_task(
        db, make_account):
    """spec §7.3 / decisions 5a & 2: a resolved servicer-raised relocate, after
    the real ``relocate_stay`` re-bind + linked-Glitch close, spawns EXACTLY
    ONE ``ChildSubRequest`` reusing the triggering child's ``request_id`` with
    ``predecessor_child_id`` = the triggering child, plus EXACTLY ONE
    ``WorkOrder kind='relocation_move'`` driven through the EXISTING C4 routing
    path, visible on the existing servicer-tasks read path, with exactly one
    append-only event per transition for the spawn."""
    from conduit.servicer.dal import tasks as tdal
    from conduit.shared.models import (ChildSubRequest, EventChildRouted,
                                       EventWorkOrderCreated, RecRelocate,
                                       Roster, RosterAssignment, StaffProfile)

    h = await _seed_servicer_raised_relocate(db, make_account,
                                             n_eligible_rooms=1)
    fo_ic = await _seed_fo_guest_move_code(db)
    actor = await make_account("supervisor", f"sup-{uuid.uuid4().hex[:8]}")

    # A front-office servicer who is the positional OWNER of the section the
    # relocated stay re-binds into → section_pooled routing assigns the move
    # WO to them → it surfaces as a PUSHED task on the existing servicer queue.
    fo = await make_account("servicer", f"fo-{uuid.uuid4().hex[:8]}")
    db.add(StaffProfile(account_id=fo.id, staff_class="runner",
                        presence="working", status="active"))
    now = dt.datetime.now(dt.timezone.utc)
    roster = Roster(property_id=h["prop"].id,
                    shift_start=now - dt.timedelta(hours=1),
                    shift_end=now + dt.timedelta(hours=8), status="active")
    db.add(roster)
    await db.flush()
    db.add(RosterAssignment(roster_id=roster.id, account_id=fo.id,
                            section_id=h["section"].id,
                            assignment="owner", status="active"))
    await db.flush()

    await open_escalation(db, h["child"], EscalationTrigger.SERVICER_RAISED)
    await db.flush()
    esc = (await db.execute(
        sa.select(Escalation).where(Escalation.child_id == h["child"].id)
    )).scalar_one()
    persisted = (await db.execute(
        sa.select(RecRelocate.target_room_id)
        .where(RecRelocate.recommendation_escalation_id == esc.id)
    )).scalar_one()
    assert persisted == h["eligible_rooms"][0].id

    trigger_child_id = h["child"].id
    trigger_request_id = h["child"].request_id

    await apply_recommendation(db, esc, outcome="approved", actor=actor.id)
    await db.flush()

    # The real relocate_stay re-bind + linked Glitch close still hold.
    st = (await db.execute(
        sa.select(Stay).where(Stay.id == h["stay"].id))).scalar_one()
    assert st.room_id == persisted
    gl = (await db.execute(
        sa.select(Glitch).where(Glitch.id == h["glitch"].id))).scalar_one()
    assert gl.state in ("closed", "auto_closed")

    # EXACTLY ONE move child: same request_id, predecessor = the trigger child,
    # FO-GUEST-MOVE issue code, dispatch.
    moves = (await db.execute(
        sa.select(ChildSubRequest).where(
            ChildSubRequest.predecessor_child_id == trigger_child_id)
    )).scalars().all()
    assert len(moves) == 1
    mv = moves[0]
    assert mv.request_id == trigger_request_id
    assert mv.id != trigger_child_id
    assert mv.issue_code_id == fo_ic.id
    assert mv.fulfilment_mode == "dispatch"

    # EXACTLY ONE WorkOrder kind='relocation_move' linked to the move child.
    wos = (await db.execute(
        sa.select(WorkOrder).where(WorkOrder.child_id == mv.id)
    )).scalars().all()
    assert len(wos) == 1
    assert wos[0].kind == "relocation_move"

    # Visible on the existing servicer-tasks read path (the front-office
    # owner's queue) — just another task card.
    cards = await tdal.list_tasks(db, fo.id)
    assert any(str(c["work_order_id"]) == str(wos[0].id) for c in cards)

    # Exactly one append-only event per transition for the spawn: the move
    # child's single child_routed + the move WO's single work_order_created.
    n_routed = (await db.execute(
        sa.select(sa.func.count()).select_from(EventChildRouted)
        .where(EventChildRouted.child_id == mv.id))).scalar_one()
    assert n_routed == 1
    n_wo_created = (await db.execute(
        sa.select(sa.func.count()).select_from(EventWorkOrderCreated)
        .where(EventWorkOrderCreated.work_order_id == wos[0].id)
    )).scalar_one()
    assert n_wo_created == 1

    # Idempotency / blast-radius: exactly ONE move child + WO total.
    total_moves = (await db.execute(
        sa.select(sa.func.count()).select_from(ChildSubRequest)
        .where(ChildSubRequest.predecessor_child_id == trigger_child_id)
    )).scalar_one()
    assert total_moves == 1
    total_move_wos = (await db.execute(
        sa.select(sa.func.count()).select_from(WorkOrder)
        .where(WorkOrder.kind == "relocation_move")
    )).scalar_one()
    assert total_move_wos == 1

