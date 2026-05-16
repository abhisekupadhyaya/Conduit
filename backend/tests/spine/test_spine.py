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

from conduit.shared.engine.spine import EscalationTrigger, open_escalation
from conduit.shared.models import (Account, Escalation, EscalationLadder,
                                   Event, EventEscalationOpened,
                                   EventRecommendationCreated, IssueCode,
                                   Property, RecBroadcast, RecReassign,
                                   Recommendation, Request, Roster,
                                   RosterAssignment, Room, Section, SLAPreset,
                                   StaffProfile, Stay, Timer)

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
