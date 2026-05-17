import datetime as dt, uuid, pytest
from conduit.shared.engine import timers
from conduit.shared.models import Timer
from sqlalchemy import select

@pytest.mark.asyncio
async def test_arm_writes_pending_timer(db, make_child):
    child = await make_child(db)
    await timers.arm(db, "child_id", child.id, timers.TimerType.ACCEPT_WINDOW,
                     fire_at=dt.datetime.now(dt.UTC) + dt.timedelta(minutes=15))
    await db.flush()
    rows = (await db.execute(select(Timer).where(Timer.child_id == child.id))).scalars().all()
    assert len(rows) == 1 and rows[0].state == "pending" and rows[0].type == "accept_window"

@pytest.mark.asyncio
async def test_cancel_for_marks_cancelled(db, make_child):
    child = await make_child(db)
    await timers.arm(db, "child_id", child.id, timers.TimerType.FULFILMENT_SLA,
                     fire_at=dt.datetime.now(dt.UTC))
    await db.flush()
    await timers.cancel_for(db, "child_id", child.id)
    await db.flush()
    rows = (await db.execute(select(Timer).where(Timer.child_id == child.id))).scalars().all()
    assert all(r.state == "cancelled" for r in rows)


from conduit.shared.engine import runner


@pytest.mark.asyncio
async def test_tick_fires_only_due_pending(db, make_child):
    child = await make_child(db)
    from conduit.shared.engine import timers
    past = dt.datetime.now(dt.UTC) - dt.timedelta(seconds=1)
    future = dt.datetime.now(dt.UTC) + dt.timedelta(hours=1)
    await timers.arm(db, "child_id", child.id, timers.TimerType.ACCEPT_WINDOW, fire_at=past)
    await timers.arm(db, "child_id", child.id, timers.TimerType.FULFILMENT_SLA, fire_at=future)
    await db.flush()
    fired = await runner.tick(db)
    assert fired == 1   # only the past one


from conduit.shared.engine import sweeper


@pytest.mark.asyncio
async def test_sweep_flags_overdue_unfired(db, make_child):
    child = await make_child(db)
    from conduit.shared.engine import timers
    await timers.arm(db, "child_id", child.id, timers.TimerType.ACCEPT_WINDOW,
                     fire_at=dt.datetime.now(dt.UTC) - dt.timedelta(hours=1))
    await db.flush()
    overdue = await sweeper.sweep(db)
    assert overdue >= 1


# ===========================================================================
# Task D3 — runner stall->spine->auto-proceed->backstop wiring (Spec §7.3)
# ===========================================================================

import sqlalchemy as sa

from conduit.shared.engine import spine
from conduit.shared.models import (Account, ChildSubRequest, Escalation,
                                   EscalationLadder, EventEscalationOpened,
                                   EventEscalationResolved, FailedTransition,
                                   IssueCode, Property, Recommendation,
                                   RecReassign, RecBroadcast, Request, Roster,
                                   RosterAssignment, Room, Section, SLAPreset,
                                   StaffProfile, Stay, WorkOrder)

D3_ACCEPT_WINDOW_SECONDS = 120
D3_FULFILMENT_SLA_SECONDS = 1800
D3_SUPERVISOR_SLA_SECONDS = 900


async def _seed_routed_child(db, make_account, *, n_cycle_bound=2):
    """Full FK chain Property→Section→Room→Stay→Request→Child + a routed
    WorkOrder + a fresh non-stalled servicer C1 routing.select will pick.

    Mirrors the D2 ``_seed_stall_scenario`` idiom (test_spine.py) but stops
    BEFORE opening the escalation — D3 drives that through the runner/spine.
    Returns the seeded handles.
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
                    accept_window_seconds=D3_ACCEPT_WINDOW_SECONDS,
                    fulfilment_sla_seconds=D3_FULFILMENT_SLA_SECONDS,
                    supervisor_sla_seconds=D3_SUPERVISOR_SLA_SECONDS,
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
    child = ChildSubRequest(request_id=r.id, text="x", outcome="auto",
                            state="in_progress", issue_code_id=ic.id,
                            priority_tier="P3")
    db.add(child)
    await db.flush()

    wo = WorkOrder(child_id=child.id, kind="dispatch",
                   routing_model="skill_matched", priority_tier="P3",
                   assigned_servicer_id=stalled.id,
                   accountable_owner_id=owner.id,
                   section_id=sec.id, state="created")
    db.add(wo)
    await db.flush()

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

    return {"child": child, "prop": p, "sla": sla, "wo": wo,
            "owner": owner, "stalled": stalled, "target": target,
            "section": sec, "stay": stay, "room": room, "duty": duty}


@pytest.mark.asyncio
async def test_d3_accept_window_breach_stalls_to_spine(db, make_account):
    """accept_window breach on a routed child with no accept → STALL:
    spine.open_escalation(child, 'stall') ran (Escalation(stall, open) with a
    deterministic reassign Recommendation), the child's revised_eta is set
    (D22, not None and in the future), exactly one escalation_opened event,
    and the timer is now 'fired' (not pending). tick returned >=1."""
    h = await _seed_routed_child(db, make_account)
    from conduit.shared.engine import timers as t
    db_now = (await db.execute(sa.select(sa.func.now()))).scalar_one()
    await t.arm(db, "child_id", h["child"].id, t.TimerType.ACCEPT_WINDOW,
                fire_at=db_now - dt.timedelta(seconds=5))
    await db.flush()

    fired = await runner.tick(db)
    assert fired >= 1

    esc = (await db.execute(
        sa.select(Escalation).where(Escalation.child_id == h["child"].id)
    )).scalars().all()
    assert len(esc) == 1
    esc = esc[0]
    assert esc.trigger == "stall" and esc.state == "open"

    rec = (await db.execute(
        sa.select(Recommendation)
        .where(Recommendation.escalation_id == esc.id))).scalar_one()
    assert rec.action in ("reassign", "broadcast")
    if rec.action == "reassign":
        d = (await db.execute(sa.select(RecReassign).where(
            RecReassign.recommendation_escalation_id == esc.id))).scalar_one()
        assert d.target_account_id == h["target"].id

    # D22: the child is proactively told "running late" — revised_eta set.
    ch = (await db.execute(sa.select(ChildSubRequest)
          .where(ChildSubRequest.id == h["child"].id))).scalar_one()
    assert ch.revised_eta is not None
    assert ch.revised_eta > db_now

    opened = (await db.execute(
        sa.select(EventEscalationOpened)
        .where(EventEscalationOpened.escalation_id == esc.id)
    )).scalars().all()
    assert len(opened) == 1

    tmr = (await db.execute(sa.select(Timer).where(
        Timer.child_id == h["child"].id,
        Timer.type == "accept_window"))).scalar_one()
    assert tmr.state == "fired"


async def _arm_open_stall_esc(db, h, *, cycle_count):
    """Seed an OPEN stall Escalation (with the stored reassign Rec the
    auto-proceed will execute) at a GIVEN ``cycle_count``.

    NOTE: this hand-sets ``cycle_count`` and therefore can ONLY back a
    "runner→spine honors the D21 bound for a given cycle_count" unit
    assertion — it does NOT (and must not) be used to claim the production
    open_escalation→auto-proceed→open_escalation carry-forward chain. The
    real-chain backstop is proven in
    ``test_d3_supervisor_sla_auto_proceeds_then_hard_escalates`` below, which
    NEVER hand-sets cycle_count (it comes from the real spine carry-forward).
    """
    esc = Escalation(child_id=h["child"].id, trigger="stall", state="open",
                     cycle_count=cycle_count, raised_by_account_id=None)
    db.add(esc)
    await db.flush()
    db.add(Recommendation(escalation_id=esc.id, action="reassign",
                          rationale_text="reassign to the routed target"))
    await db.flush()
    db.add(RecReassign(recommendation_escalation_id=esc.id,
                       target_account_id=h["target"].id))
    await db.flush()
    db_now = (await db.execute(sa.select(sa.func.now()))).scalar_one()
    from conduit.shared.engine import timers as t
    await t.arm(db, "escalation_id", esc.id, t.TimerType.SUPERVISOR_SLA,
                fire_at=db_now - dt.timedelta(seconds=5))
    await db.flush()
    return esc


async def _arm_stall_timer_in_past(db, child_id):
    """Arm an accept_window timer in the past on the child → the next
    ``runner.tick`` opens a stall Escalation through the REAL spine
    (runner._fire_one → spine.open_escalation(child, 'stall')). Used to
    represent both the initial stall and the post-reassign stall.

    The C4/spine reassign effect (spine._execute_action) swaps the
    WorkOrder assignee IN PLACE and does NOT re-arm an accept_window timer
    in this slice (the post-reassign re-arm is Phase-E surface). Arming a
    fresh accept_window timer on the SAME child is therefore the faithful
    production representation of "the reassigned work also stalls": it
    drives the identical runner→spine.open_escalation hop the first stall
    took, so cycle 2's escalation cycle_count comes ENTIRELY from the real
    spine carry-forward, never hand-set."""
    db_now = (await db.execute(sa.select(sa.func.now()))).scalar_one()
    from conduit.shared.engine import timers as t
    await t.arm(db, "child_id", child_id, t.TimerType.ACCEPT_WINDOW,
                fire_at=db_now - dt.timedelta(seconds=5))
    await db.flush()


async def _arm_supervisor_sla_in_past(db, esc_id):
    """Arm the escalation's supervisor_sla timer in the past → the next
    ``runner.tick`` auto-proceeds it through the REAL spine
    (runner._fire_one → spine.apply_recommendation(auto_proceeded))."""
    db_now = (await db.execute(sa.select(sa.func.now()))).scalar_one()
    from conduit.shared.engine import timers as t
    await t.arm(db, "escalation_id", esc_id, t.TimerType.SUPERVISOR_SLA,
                fire_at=db_now - dt.timedelta(seconds=5))
    await db.flush()


@pytest.mark.asyncio
async def test_d3_runner_spine_honors_d21_bound_for_given_cycle_count(
        db, make_account):
    """Runner→spine dispatch honors the D21 bound for a GIVEN cycle_count
    (a hand-seeded unit assertion — NOT the production carry-forward chain;
    see ``test_d3_supervisor_sla_auto_proceeds_then_hard_escalates`` for the
    real chain). At cycle_count=0 the supervisor_sla breach auto-proceeds
    (state auto_proceeded, resolved_by None, count→1, reassign executed);
    at cycle_count=1 with n_cycle_bound=2 the runner→spine dispatch
    hard-escalates INSTEAD (D21, enforced internally by D2 — the runner just
    calls apply_recommendation)."""
    h = await _seed_routed_child(db, make_account, n_cycle_bound=2)

    # cycle_count=0 → apply_recommendation(auto_proceeded) → auto_proceeds.
    esc1 = await _arm_open_stall_esc(db, h, cycle_count=0)
    fired = await runner.tick(db)
    assert fired >= 1

    er1 = (await db.execute(sa.select(Escalation)
           .where(Escalation.id == esc1.id))).scalar_one()
    # The structural silence ≡ approve path.
    assert er1.state == "auto_proceeded"
    assert er1.resolved_by_account_id is None
    assert er1.cycle_count == 1
    resolved1 = (await db.execute(sa.select(EventEscalationResolved)
                 .where(EventEscalationResolved.escalation_id == esc1.id)
                 )).scalars().all()
    assert len(resolved1) == 1
    # The reassign executed on the silent path (D2: silence ≡ approve).
    wo1 = (await db.execute(sa.select(WorkOrder)
           .where(WorkOrder.child_id == h["child"].id))).scalar_one()
    assert wo1.assigned_servicer_id == h["target"].id

    # cycle_count=1, n_cycle_bound=2: 1+1 >= 2 → the runner→spine dispatch
    # hard-escalates INSTEAD of another auto-proceed (D21, enforced by D2).
    esc2 = await _arm_open_stall_esc(db, h, cycle_count=1)
    fired2 = await runner.tick(db)
    assert fired2 >= 1

    er2 = (await db.execute(sa.select(Escalation)
           .where(Escalation.id == esc2.id))).scalar_one()
    assert er2.state == "hard_escalated"
    assert er2.resolved_by_account_id is None
    # No further auto-proceed: cycle_count is NOT bumped on the hard-escalate
    # path (the D21 backstop, not a resolution).
    assert er2.cycle_count == 1
    resolved2 = (await db.execute(sa.select(EventEscalationResolved)
                 .where(EventEscalationResolved.escalation_id == esc2.id)
                 )).scalars().all()
    assert len(resolved2) == 1


@pytest.mark.asyncio
async def test_d3_supervisor_sla_auto_proceeds_then_hard_escalates(
        db, make_account):
    """The REAL D21 production backstop chain (Spec §9.2/§7.4 D21), driven
    end-to-end through the runner + spine with NO hand-set cycle_count.

    n_cycle_bound=2. Cycle 1: a stall opens an Escalation via the real
    spine.open_escalation (cycle_count==0, no prior stall esc); its
    supervisor_sla breach auto-proceeds (silence ≡ approve), reassigning the
    work and advancing the running count to 1. Cycle 2: the reassigned work
    ALSO stalls — a fresh stall opens a NEW Escalation via the real
    spine.open_escalation, whose cycle_count==1 comes ENTIRELY from the
    spine's stall-chain carry-forward (the prior stall esc was advanced to 1
    by apply_recommendation); its supervisor_sla breach now hits the D21
    bound (1+1 >= 2) → hard_escalate. The backstop is reachable in
    production ONLY because open_escalation carries the count forward."""
    h = await _seed_routed_child(db, make_account, n_cycle_bound=2)
    child_id = h["child"].id

    # --- Cycle 1: the initial stall opens an Escalation via the REAL spine.
    await _arm_stall_timer_in_past(db, child_id)
    fired = await runner.tick(db)
    assert fired >= 1

    esc1 = (await db.execute(
        sa.select(Escalation).where(Escalation.child_id == child_id)
    )).scalars().all()
    assert len(esc1) == 1
    esc1 = esc1[0]
    assert esc1.trigger == "stall" and esc1.state == "open"
    # First stall for a fresh child → no prior stall esc → count starts at 0
    # (the spine carry-forward seeds 0 when there is no prior; preserves D1).
    assert esc1.cycle_count == 0

    # supervisor_sla breach → real apply_recommendation(auto_proceeded).
    await _arm_supervisor_sla_in_past(db, esc1.id)
    fired = await runner.tick(db)
    assert fired >= 1

    er1 = (await db.execute(sa.select(Escalation)
           .where(Escalation.id == esc1.id))).scalar_one()
    assert er1.state == "auto_proceeded"          # structural silence path
    assert er1.resolved_by_account_id is None
    assert er1.cycle_count == 1                    # advanced by D2
    # The reassign effect ran (the work was handed to the routed target).
    wo1 = (await db.execute(sa.select(WorkOrder)
           .where(WorkOrder.child_id == child_id))).scalar_one()
    assert wo1.assigned_servicer_id == h["target"].id

    # --- Cycle 2: the REASSIGNED work also stalls. The spine reassign effect
    # swaps the assignee in place and does NOT re-arm an accept_window timer
    # in this slice; arming a fresh accept_window timer on the SAME child is
    # the faithful production representation — it drives the identical
    # runner→spine.open_escalation hop. cycle_count on the new escalation
    # MUST come from the real spine carry-forward, NOT hand-set.
    await _arm_stall_timer_in_past(db, child_id)
    fired = await runner.tick(db)
    assert fired >= 1

    all_esc = (await db.execute(
        sa.select(Escalation).where(Escalation.child_id == child_id)
        .order_by(Escalation.created_at)
    )).scalars().all()
    assert len(all_esc) == 2  # a NEW stall escalation opened
    esc2 = all_esc[1]
    assert esc2.id != esc1.id
    assert esc2.trigger == "stall" and esc2.state == "open"
    # CARRY-FORWARD PROVEN: the new stall escalation inherits the running
    # count from the prior (auto-proceeded) stall escalation via the real
    # spine.open_escalation — NOT hand-set anywhere in this test.
    assert esc2.cycle_count == 1

    # supervisor_sla breach on cycle 2 → real apply_recommendation: the D21
    # bound is now reachable in production (1+1 >= n_cycle_bound(2)).
    await _arm_supervisor_sla_in_past(db, esc2.id)
    fired = await runner.tick(db)
    assert fired >= 1

    er2 = (await db.execute(sa.select(Escalation)
           .where(Escalation.id == esc2.id))).scalar_one()
    assert er2.state == "hard_escalated"          # D21 backstop reached
    assert er2.resolved_by_account_id is None
    # hard_escalate does not bump cycle_count (it is the backstop, not a
    # resolution); no further auto-proceed/reassign occurred.
    assert er2.cycle_count == 1
    resolved2 = (await db.execute(sa.select(EventEscalationResolved)
                 .where(EventEscalationResolved.escalation_id == esc2.id)
                 )).scalars().all()
    assert len(resolved2) == 1
    # No third escalation, no further reassign side effect.
    final_esc = (await db.execute(
        sa.select(Escalation).where(Escalation.child_id == child_id)
    )).scalars().all()
    assert len(final_esc) == 2


@pytest.mark.asyncio
async def test_d3_backstop_cycle_hard_escalates(db, make_account):
    """backstop_cycle timer in the past → spine.hard_escalate ran:
    escalation state hard_escalated, the timer is fired."""
    h = await _seed_routed_child(db, make_account)
    from conduit.shared.engine import timers as t
    esc = Escalation(child_id=h["child"].id, trigger="stall", state="open",
                     cycle_count=0, raised_by_account_id=None)
    db.add(esc)
    await db.flush()

    db_now = (await db.execute(sa.select(sa.func.now()))).scalar_one()
    await t.arm(db, "escalation_id", esc.id, t.TimerType.BACKSTOP_CYCLE,
                fire_at=db_now - dt.timedelta(seconds=5))
    await db.flush()

    fired = await runner.tick(db)
    assert fired >= 1

    esc_row = (await db.execute(sa.select(Escalation)
               .where(Escalation.id == esc.id))).scalar_one()
    assert esc_row.state == "hard_escalated"
    tmr = (await db.execute(sa.select(Timer).where(
        Timer.escalation_id == esc.id,
        Timer.type == "backstop_cycle"))).scalar_one()
    assert tmr.state == "fired"


@pytest.mark.asyncio
async def test_d3_failing_spine_call_dead_letters_and_loop_survives(
        db, make_account):
    """B2 invariant preserved: a timer whose spine call genuinely errors is
    dead-lettered to failed_transitions and the loop survives — a sibling
    healthy timer in the same tick still fires."""
    h = await _seed_routed_child(db, make_account)
    from conduit.shared.engine import timers as t

    # Bad timer: an accept_window stall on a child whose property has NO
    # active EscalationLadder → spine.open_escalation raises ConflictError
    # (its own real guard). Realistic, minimal, exercises the runner→spine
    # dispatch failure path.
    bad_guest = await make_account("guest", f"bg-{uuid.uuid4().hex[:8]}")
    bad_p = Property(name="NoLadder")
    db.add(bad_p)
    await db.flush()
    bad_sec = Section(property_id=bad_p.id, label="S")
    db.add(bad_sec)
    await db.flush()
    bad_room = Room(section_id=bad_sec.id, label="R")
    db.add(bad_room)
    await db.flush()
    bnow = dt.datetime.now(dt.timezone.utc)
    bad_stay = Stay(guest_account_id=bad_guest.id, room_id=bad_room.id,
                    check_in=bnow, check_out=bnow + dt.timedelta(days=1),
                    status="active")
    db.add(bad_stay)
    await db.flush()
    bad_req = Request(guest_account_id=bad_guest.id, stay_id=bad_stay.id,
                      raw_text="orphan-ladder")
    db.add(bad_req)
    await db.flush()
    orphan_child = ChildSubRequest(request_id=bad_req.id, text="x",
                                   outcome="auto", state="in_progress")
    db.add(orphan_child)
    await db.flush()

    db_now = (await db.execute(sa.select(sa.func.now()))).scalar_one()
    await t.arm(db, "child_id", orphan_child.id, t.TimerType.ACCEPT_WINDOW,
                fire_at=db_now - dt.timedelta(seconds=10))
    # Sibling healthy timer (accept_window stall) claimed in the same tick.
    await t.arm(db, "child_id", h["child"].id, t.TimerType.ACCEPT_WINDOW,
                fire_at=db_now - dt.timedelta(seconds=5))
    await db.flush()

    fired = await runner.tick(db)
    assert fired >= 2  # both claimed; the bad one counts (never silent)

    # The bad timer was dead-lettered.
    bad_tmr = (await db.execute(sa.select(Timer).where(
        Timer.child_id == orphan_child.id,
        Timer.type == "accept_window"))).scalar_one()
    failed = (await db.execute(sa.select(FailedTransition).where(
        FailedTransition.timer_id == bad_tmr.id))).scalars().all()
    assert len(failed) == 1
    assert bad_tmr.state == "pending"  # not marked fired (savepoint rolled)

    # The loop survived: the healthy sibling stall fired end-to-end.
    esc = (await db.execute(sa.select(Escalation)
           .where(Escalation.child_id == h["child"].id))).scalar_one()
    assert esc.trigger == "stall" and esc.state == "open"
    good_tmr = (await db.execute(sa.select(Timer).where(
        Timer.child_id == h["child"].id,
        Timer.type == "accept_window"))).scalar_one()
    assert good_tmr.state == "fired"
