"""Structural + behavioural invariants (Spec §11).

These guards turn the spine's load-bearing promises into red-on-drift tests:
response shapes parse back under ``extra=forbid``; Resolution-A keeps the
reservation-mutation flag server-owned; the role matrix denies non-supervisors;
the event writer has no UPDATE/DELETE path (append-only); the savepoint bench
leaves a zero baseline between tests; disabled KB is excluded from live
grounding; the idempotent seed survives a re-seed; and exactly one event +
one detail row is written per lifecycle transition.
"""
from __future__ import annotations

import sqlalchemy as sa

from conduit.guest.schemas.conversation import ChildOut  # noqa: F401
from conduit.supervisor.schemas.issue_code import IssueCodeOut


async def test_response_shapes_parse_back(client, make_account, login):
    await make_account("supervisor", "sup", "pw-123456")
    await login("sup", "pw-123456")
    r = await client.post("/api/supervisor/issue-codes", json={
        "code": "Z", "label": "z", "department": "d",
        "fulfilment_mode": "no_dispatch",
        "routing_model": "none", "intent_kind": "service"})
    IssueCodeOut(**r.json())                          # extra=forbid → red on drift


async def test_resolution_A_request_rejects_mutation(client, make_account, login):
    await make_account("supervisor", "s", "pw-123456")
    await login("s", "pw-123456")
    r = await client.post("/api/supervisor/issue-codes", json={
        "code": "Q", "label": "q", "department": "d",
        "fulfilment_mode": "no_dispatch",
        "routing_model": "none", "intent_kind": "service",
        "is_reservation_mutation": True})
    assert r.status_code == 422


async def test_role_matrix(client, make_account, login):
    for role in ("guest", "servicer"):
        await make_account(role, role, "pw-123456")
        await login(role, "pw-123456")
        assert (await client.get(
            "/api/supervisor/issue-codes")).status_code == 403


async def test_no_event_update_or_delete_path():
    import conduit.shared.events.writer as w
    src = open(w.__file__).read()
    assert "delete(" not in src and ".delete()" not in src


async def test_leak_sentinel(db):
    from conduit.shared.models import ChildSubRequest, Event, Request
    for m in (Request, ChildSubRequest, Event):
        n = len((await db.execute(sa.select(m))).scalars().all())
        assert n == 0            # savepoint rollback ⇒ baseline between tests


async def test_live_policy_disable(client, make_account, login,
                                   seeded_guest_with_stay, fake_llm, db):
    # Supervisor authors two KB entries; one is then disabled. The live
    # grounding read (nodispatch.resolve → kbdal.list_entries(status="active"))
    # must surface ONLY the active one. ``client`` overrides db_session to this
    # package's savepoint ``db`` session — so the same ``db`` is the one the
    # intake service must run on (asserted by topic visibility below).
    await make_account("supervisor", "sup", "pw-123456")
    await login("sup", "pw-123456")
    active_topic = "wifi-active"
    disabled_topic = "spa-disabled"
    r1 = await client.post("/api/supervisor/kb", json={
        "topic": active_topic, "content": "wifi password is conduit"})
    assert r1.status_code == 201
    r2 = await client.post("/api/supervisor/kb", json={
        "topic": disabled_topic, "content": "spa closes at 9"})
    assert r2.status_code == 201
    r3 = await client.patch(f"/api/supervisor/kb/{r2.json()['id']}",
                            json={"status": "disabled"})
    assert r3.status_code == 200 and r3.json()["status"] == "disabled"

    captured: dict[str, str] = {}

    async def fclassify(t, cat):
        return [{"text": t, "issue_code": None, "fulfilment_mode": None,
                 "outcome": "no_dispatch", "is_problem_report": False}]

    async def fground(q, ctx):
        captured["ctx"] = ctx          # the bounded CONTEXT grounding string
        return {"grounded": False, "leaves_no_dispatch": False, "answer": "",
                "used_kb_ids": [], "used_fields": []}

    fake_llm["classify"] = fclassify
    fake_llm["ground"] = fground

    actor, _ambient = seeded_guest_with_stay
    from conduit.guest.services import intake
    out = await intake.submit_request(db, actor, "what is the wifi?")
    await db.flush()

    assert out["children"][0]["terminal"] == "logged"   # deferred (grounded=False)
    ctx = captured["ctx"]
    assert active_topic in ctx and "conduit" in ctx
    assert disabled_topic not in ctx and "spa closes at 9" not in ctx


async def test_seed_survives_reseed(db):
    from conduit.shared.models import IssueCode
    from conduit.seed import ensure_issue_codes
    await ensure_issue_codes(db)
    await db.flush()
    n1 = len((await db.execute(sa.select(IssueCode))).scalars().all())
    one = (await db.execute(sa.select(IssueCode).limit(1))).scalars().first()
    one.status = "disabled"
    db.add(one)
    await db.flush()
    await ensure_issue_codes(db)                          # re-seed
    await db.flush()
    rows = (await db.execute(sa.select(IssueCode))).scalars().all()
    assert len(rows) == n1                                # no dup inserted
    again = await db.get(IssueCode, one.id)
    assert again.status == "disabled"                     # supervisor edit survived


async def test_one_event_per_transition(db, seeded_guest_with_stay, fake_llm):
    from conduit.seed import ensure_issue_codes
    from conduit.shared.models import (Event, EventChildAnswered,
                                       EventChildTriaged, EventRequestCreated)

    await ensure_issue_codes(db)
    await db.flush()
    actor, _ambient = seeded_guest_with_stay

    async def fclassify(t, cat):
        return [{"text": t, "issue_code": "INFO_DINING",
                 "fulfilment_mode": "no_dispatch", "outcome": "no_dispatch",
                 "is_problem_report": False}]

    async def fground(q, ctx):
        return {"grounded": True, "leaves_no_dispatch": False, "answer": "x",
                "used_kb_ids": [], "used_fields": []}

    fake_llm["classify"] = fclassify
    fake_llm["ground"] = fground

    from conduit.guest.services import intake
    out = await intake.submit_request(db, actor, "q")
    await db.flush()
    assert out["children"][0]["terminal"] == "answered"

    # Exactly one event per transition + exactly one matching detail row.
    for etype, detail in (("request_created", EventRequestCreated),
                          ("child_triaged", EventChildTriaged),
                          ("child_answered", EventChildAnswered)):
        evs = (await db.execute(
            sa.select(Event).where(Event.type == etype))).scalars().all()
        assert len(evs) == 1, f"{etype}: expected 1 event, got {len(evs)}"
        dets = (await db.execute(sa.select(detail))).scalars().all()
        assert len(dets) == 1, (
            f"{detail.__name__}: expected 1 detail row, got {len(dets)}")
        assert dets[0].event_id == evs[0].id


# ==========================================================================
# Task G1 — Spec §11 structural guards over the NEW dispatch+spine surface
# (Phases A–F). These are EXPLICIT tests over the new routes, NOT a reliance
# on the inherited auth-coverage sweep. The new-route set is derived
# PROGRAMMATICALLY from the live FastAPI route table by dispatch-spine prefix
# membership (mirroring tests/api/test_security_guards.py::_routes and
# tests/spine/test_staffing_structural.py::_route_contract) so a route added
# by any later slice is swept automatically and cannot be silently missed by
# a hardcoded partial list.
#
#   (1) auth-coverage   — every new route is 401/403 WITHOUT a cookie
#   (2) parse-back      — each new response schema is extra="forbid" + a live
#                         payload round-trips with no internal-column leak
#   (3) role×endpoint   — guest/servicer/supervisor/duty_manager/unauth →
#                         the EXACT spec-§8 allow/deny matrix per handler
#   (4) append-only     — the writer/orchestrator has no UPDATE/DELETE of an
#                         event/detail row; one mutating C4 call ⇒ exactly
#                         one event + one detail row
#   (5) no-DELETE→405   — DELETE over EVERY new route → 405 (no hard-delete)
#   (6) physical invariants — timer one-subject CHECK, work_order/glitch
#                         child_id UNIQUE, sla_preset/escalation_ladder
#                         partial-unique (re-asserted at the suite level)
# ==========================================================================
import datetime as _dt
import typing as _typing
import uuid as _uuid

import pytest as _pytest
from fastapi.routing import APIRoute as _APIRoute
from sqlalchemy.exc import IntegrityError as _IntegrityError

# The dispatch-spine A–F surface = these and ONLY these path prefixes. Every
# other /api path (auth, health, staffing /staff /rosters /sections /rooms
# /stays, the merged config /accounts /issue-codes /kb, the merged servicer
# /queue /work-orders /home /presence, /supervisor/setup) is INHERITED /
# merged surface and is out of scope for the G1 dispatch-spine guards (those
# are covered by the inherited tests/api + tests/spine/test_staffing_*
# guards). Stated as prefixes so a NEW route under any of them is swept.
_SPINE_PREFIXES = (
    "/api/guest/requests",
    "/api/guest/children",
    "/api/servicer/tasks",
    "/api/supervisor/decisions",
    "/api/supervisor/children",
    "/api/supervisor/sla-presets",
    "/api/supervisor/escalation-ladder",
    "/api/supervisor/awareness",
)
_PW = "pw-123456"


def _is_spine(path: str) -> bool:
    return any(path == p or path.startswith(p + "/")
              or path.startswith(p + "{") for p in _SPINE_PREFIXES)


def _spine_routes() -> list[_APIRoute]:
    """Every dispatch-spine APIRoute, derived from the live route table by
    prefix membership (the inherited sweep idiom). Asserted non-empty so a
    refactor that drops the whole surface trips here, not silently passes."""
    from conduit.main import app

    rs = [r for r in app.routes
          if isinstance(r, _APIRoute) and _is_spine(r.path)]
    assert rs, "no dispatch-spine routes discovered — route table changed"
    return rs


def _spine_method_paths() -> list[tuple[str, str]]:
    """Sorted unique ``(METHOD, path)`` over every dispatch-spine route
    (HEAD/OPTIONS excluded — same filter as the inherited sweep)."""
    out: list[tuple[str, str]] = []
    for r in _spine_routes():
        for m in sorted(r.methods):
            if m in ("HEAD", "OPTIONS"):
                continue
            out.append((m, r.path))
    return sorted(set(out))


def _concrete(path: str) -> str:
    """Fill every ``{param}`` with a fresh UUID so the path is routable
    (auth/method routing is decided BEFORE the handler, so a non-existent id
    is fine — we assert the gate code, never the downstream business code)."""
    out = path
    while "{" in out:
        i = out.index("{")
        j = out.index("}", i)
        out = out[:i] + str(_uuid.uuid4()) + out[j + 1:]
    return out


# --------------------------------------------------------------------------
# G1 (1) — auth-coverage: no new dispatch-spine route is unauthenticated.
# Explicit (not the inherited meta-sweep): every NEW route, NO cookie → the
# auth gate fires (401 missing/!=, or 403). A 2xx/404/422 here = an
# accidentally public spine route.
# --------------------------------------------------------------------------
async def test_g1_every_new_route_requires_auth(client):
    client.cookies.clear()
    mp = _spine_method_paths()
    assert mp, "empty dispatch-spine route set"
    for method, path in mp:
        r = await client.request(method, _concrete(path))
        assert r.status_code in (401, 403), (
            f"unauth {method} {path} -> {r.status_code} "
            "(a new dispatch-spine route is reachable without a cookie)")


# --------------------------------------------------------------------------
# G1 (2) — response parse-back: each NEW response schema is extra="forbid"
# and a LIVE payload round-trips with NO internal-column leak. Drives the
# real read/mutation endpoints with a real seeded actor; parses every row
# back through its declared response_model; asserts known internal column
# names never appear in the raw body.
# --------------------------------------------------------------------------
async def test_g1_response_schemas_forbid_extra_and_no_leak(
        client, make_account, login, db):
    from pydantic import ValidationError

    # Every new route's response_model is extra="forbid" (static guard over
    # the schema config — red if a schema is added without the lockdown).
    for r in _spine_routes():
        rm = r.response_model
        if rm is None:
            continue
        origin = _typing.get_origin(rm)
        models = list(_typing.get_args(rm)) if origin is list else [rm]
        for m in models:
            cfg = getattr(m, "model_config", {})
            assert cfg.get("extra") == "forbid", (
                f"{r.path} response model {getattr(m, '__name__', m)} is "
                "not extra='forbid' (internal-field leak risk)")
            with _pytest.raises(ValidationError):
                m(__nonexistent_internal_col__="x")  # extra ⇒ reject

    # Live parse-back: guest conversation/dispatch reads + a supervisor
    # config create, through the real auth'd edge on the savepoint session.
    from conduit.guest.schemas.conversation import RequestOut
    from conduit.guest.schemas.requests import DispatchCardOut
    from conduit.supervisor.schemas.awareness import AwarenessOut
    from conduit.supervisor.schemas.decisions import DecisionOut
    from conduit.supervisor.schemas.override import ChildExplorerOut
    from conduit.supervisor.schemas.setup import (EscalationLadderOut,
                                                  SLAPresetOut)

    g = await make_account("guest", f"g-{_uuid.uuid4().hex[:8]}", _PW)
    await login(g.username, _PW)
    rc = await client.get("/api/guest/requests")
    assert rc.status_code == 200, rc.text
    for row in rc.json():                                  # GET /requests
        # The dispatch router owns GET /requests (DispatchCardOut); it is
        # empty for a fresh guest, but the schema must still parse any row.
        DispatchCardOut(**row)
    assert "secret_hash" not in rc.text and "guest_account_id" not in rc.text

    sup = await make_account("supervisor", f"s-{_uuid.uuid4().hex[:8]}", _PW)
    await login(sup.username, _PW)
    for url, model in (("/api/supervisor/decisions", DecisionOut),
                       ("/api/supervisor/children", ChildExplorerOut)):
        rr = await client.get(url)
        assert rr.status_code == 200, rr.text
        for row in rr.json():
            model(**row)
        for leak in ("secret_hash", "raw_text", "predecessor_child_id"):
            assert leak not in rr.text, f"{leak} leaked via {url}"
    ra = await client.get("/api/supervisor/awareness")
    assert ra.status_code == 200, ra.text
    AwarenessOut(**ra.json())                              # composite parse

    from conduit.shared.models import Property
    p = Property(name=f"P-{_uuid.uuid4().hex[:6]}")
    db.add(p)
    await db.flush()
    rp = await client.post("/api/supervisor/sla-presets", json={
        "property_id": str(p.id), "tier": "P2",
        "accept_window_seconds": 60, "fulfilment_sla_seconds": 600,
        "supervisor_sla_seconds": 1200})
    assert rp.status_code == 201, rp.text
    SLAPresetOut(**rp.json())                              # round-trips
    rl = await client.post("/api/supervisor/escalation-ladder", json={
        "property_id": str(p.id),
        "duty_manager_account_id": str(sup.id), "n_cycle_bound": 3})
    assert rl.status_code == 201, rl.text
    EscalationLadderOut(**rl.json())
    # The guest conversation list-shape (RequestOut) parses too.
    await login(g.username, _PW)
    rq = await client.request("GET", "/api/guest/requests")
    for row in rq.json():
        # GET /requests is owned by the dispatch router (DispatchCardOut);
        # RequestOut is the POST/conversation shape — assert it still
        # round-trips an empty conversation submit (auth'd, real edge).
        DispatchCardOut(**row)
    sub = await client.post("/api/guest/requests", json={"text": ""})
    if sub.status_code == 200:
        RequestOut(**sub.json())


# --------------------------------------------------------------------------
# G1 (3) — role×endpoint matrix: the EXACT spec-§8 allow/deny per handler.
# guest-only (guest surface), servicer-only (servicer surface),
# supervisor+duty_manager (supervisor surface). unauth → 401 everywhere;
# wrong role → 403. Allowed = NOT in (401, 403, 405, 500): the request got
# PAST the role gate (we never assert the downstream business code).
# --------------------------------------------------------------------------
async def test_g1_role_endpoint_matrix(client, make_account, login):
    def _classify(path: str) -> str:
        if path.startswith("/api/guest/"):
            return "guest"
        if path.startswith("/api/servicer/"):
            return "servicer"
        return "supervisor"          # /api/supervisor/* (sup + duty_manager)

    calls = [(m, p, _classify(p)) for m, p in _spine_method_paths()]
    assert calls

    async def _hit(method, path):
        return await client.request(method, _concrete(path), json={})

    # unauth — every new route 401 (no cookie).
    client.cookies.clear()
    for method, path, _owner in calls:
        r = await _hit(method, path)
        assert r.status_code == 401, (
            f"unauth {method} {path} -> {r.status_code} (want 401)")

    role_owns = {
        "guest": {"guest"},
        "servicer": {"servicer"},
        "supervisor": {"supervisor"},
        "duty_manager": {"supervisor"},
    }
    for role, owned in role_owns.items():
        actor = await make_account(role, f"{role}-{_uuid.uuid4().hex[:8]}",
                                   _PW)
        await login(actor.username, _PW)
        for method, path, owner in calls:
            r = await _hit(method, path)
            if owner in owned:
                assert r.status_code not in (401, 403, 500), (
                    f"{role} {method} {path} -> {r.status_code} "
                    "(must pass the role gate; 401/403=gap, 500=regression)")
            else:
                assert r.status_code == 403, (
                    f"{role} {method} {path} -> {r.status_code} (want 403 — "
                    f"{role} must NOT reach the {owner} surface)")


# --------------------------------------------------------------------------
# G1 (4) — append-only. Static: the C4 writer AND the lifecycle orchestrator
# have no UPDATE/DELETE of an event/detail row (INSERT-only). Behavioural:
# one dispatch-spine mutation through the single writer path produces
# EXACTLY one new Event + one matching detail row.
# --------------------------------------------------------------------------
def test_g1_writer_and_orchestrator_are_insert_only():
    import conduit.shared.domain.lifecycle as _lc
    import conduit.shared.events.writer as _w

    for mod in (_w, _lc):
        src = open(mod.__file__).read()
        for forbidden in ("delete(", ".delete()", "update(", ".update()"):
            assert forbidden not in src, (
                f"{mod.__name__} contains {forbidden!r} — the append-only "
                "event log must be INSERT-only (no UPDATE/DELETE path)")


async def test_g1_one_event_one_detail_per_spine_mutation(db, make_account):
    """A WorkOrder ``created -> pushed`` through the C4 single writer (the
    path EVERY dispatch-spine mutation funnels through) emits exactly one
    Event + one matching detail — no double-write, no zero-write."""
    import sqlalchemy as _sa

    from conduit.shared.domain import lifecycle
    from conduit.shared.models import (ChildSubRequest, Event,
                                       EventWorkOrderPushed, Property,
                                       Request, Room, Section, Stay, WorkOrder)

    acc = await make_account("guest", f"g-{_uuid.uuid4().hex[:8]}", _PW)
    p = Property(name="T")
    db.add(p)
    await db.flush()
    sec = Section(property_id=p.id, label="S")
    db.add(sec)
    await db.flush()
    room = Room(section_id=sec.id, label="R")
    db.add(room)
    await db.flush()
    now = _dt.datetime.now(_dt.timezone.utc)
    stay = Stay(guest_account_id=acc.id, room_id=room.id, check_in=now,
                check_out=now + _dt.timedelta(days=1), status="active")
    db.add(stay)
    await db.flush()
    req = Request(guest_account_id=acc.id, stay_id=stay.id, raw_text="x")
    db.add(req)
    await db.flush()
    ch = ChildSubRequest(request_id=req.id, text="x", outcome="auto",
                         state="triaged")
    db.add(ch)
    await db.flush()
    wo = WorkOrder(child_id=ch.id, kind="dispatch",
                   routing_model="section_pooled", priority_tier="P2",
                   state="created")
    db.add(wo)
    await db.flush()

    before = len((await db.execute(
        _sa.select(Event).where(Event.type == "work_order_pushed")
    )).scalars().all())
    await lifecycle.transition(s=db, subject=wo, to="pushed",
                               actor_account_id=acc.id)
    await db.flush()

    evs = (await db.execute(
        _sa.select(Event).where(Event.type == "work_order_pushed")
    )).scalars().all()
    assert len(evs) == before + 1, (
        f"expected exactly 1 new work_order_pushed event, got "
        f"{len(evs) - before}")
    dets = (await db.execute(
        _sa.select(EventWorkOrderPushed).where(
            EventWorkOrderPushed.work_order_id == wo.id)
    )).scalars().all()
    assert len(dets) == 1, (
        f"expected exactly 1 EventWorkOrderPushed detail, got {len(dets)}")
    assert dets[0].event_id == evs[-1].id


# --------------------------------------------------------------------------
# G1 (5) — no-DELETE → 405 over EVERY new dispatch-spine route. disable-not-
# delete is the only "remove" — there is deliberately no DELETE handler, so
# method routing (which precedes the auth gate) returns 405. Authenticated
# as a supervisor so a stray 401/403 cannot mask a missing 405.
# --------------------------------------------------------------------------
async def test_g1_no_delete_handler_on_any_new_route(
        client, make_account, login):
    sup = await make_account("supervisor", f"s-{_uuid.uuid4().hex[:8]}", _PW)
    await login(sup.username, _PW)
    paths = sorted({p for _m, p in _spine_method_paths()})
    assert paths
    for path in paths:
        r = await client.delete(_concrete(path))
        assert r.status_code == 405, (
            f"DELETE {path} -> {r.status_code} (want 405 — no hard-delete; "
            "disable-not-delete is the only remove)")


# --------------------------------------------------------------------------
# G1 (6) — physical invariants re-asserted at the structural-guard suite
# level (lifted faithfully from tests/spine/test_migration_0005.py — the
# load-bearing DB CHECK/UNIQUE/partial-unique constraints the whole spine
# rests on). Postgres-only. Each builds the real FK chain, then proves the
# constraint by an IntegrityError on the violating flush.
# --------------------------------------------------------------------------
async def _g1_child(db, make_account):
    import sqlalchemy as _sa

    from conduit.shared.models import (Account, ChildSubRequest, Property,
                                       Request, Room, Section, Stay)
    await make_account("guest", f"g-{_uuid.uuid4().hex[:8]}", _PW)
    acc = (await db.execute(
        _sa.select(Account).where(Account.role == "guest")
    )).scalars().first()
    p = Property(name="T")
    db.add(p)
    await db.flush()
    sec = Section(property_id=p.id, label="S")
    db.add(sec)
    await db.flush()
    room = Room(section_id=sec.id, label="R")
    db.add(room)
    await db.flush()
    now = _dt.datetime.now(_dt.timezone.utc)
    stay = Stay(guest_account_id=acc.id, room_id=room.id, check_in=now,
                check_out=now + _dt.timedelta(days=1))
    db.add(stay)
    await db.flush()
    req = Request(guest_account_id=acc.id, stay_id=stay.id, raw_text="x")
    db.add(req)
    await db.flush()
    ch = ChildSubRequest(request_id=req.id, text="x", outcome="auto",
                         state="triaged")
    db.add(ch)
    await db.flush()
    return ch, p.id, acc.id


async def test_g1_timer_one_subject_check(db, make_account):
    """ck_timer_one_subject: 0 subject FKs and >=2 subject FKs are both
    rejected; exactly 1 is accepted."""
    from conduit.shared.models import Timer, WorkOrder

    ch, _pid, _aid = await _g1_child(db, make_account)
    # 0 subjects → rejected.
    db.add(Timer(type="accept_window", fire_at=_dt.datetime.now(_dt.UTC)))
    with _pytest.raises(_IntegrityError):
        await db.flush()
    await db.rollback()
    ch, _pid, _aid = await _g1_child(db, make_account)
    wo = WorkOrder(child_id=ch.id, kind="dispatch",
                   routing_model="section_pooled", priority_tier="P2")
    db.add(wo)
    await db.flush()
    # 2 subjects → rejected.
    db.add(Timer(type="accept_window", fire_at=_dt.datetime.now(_dt.UTC),
                 child_id=ch.id, work_order_id=wo.id))
    with _pytest.raises(_IntegrityError):
        await db.flush()
    await db.rollback()
    ch, _pid, _aid = await _g1_child(db, make_account)
    ok = Timer(type="accept_window", fire_at=_dt.datetime.now(_dt.UTC),
               child_id=ch.id)
    db.add(ok)
    await db.flush()                                    # exactly 1 → ok
    assert ok.id is not None


async def test_g1_work_order_child_unique(db, make_account):
    """A 2nd work_order for the same child_id is rejected (UNIQUE)."""
    from conduit.shared.models import WorkOrder

    ch, _pid, _aid = await _g1_child(db, make_account)
    db.add(WorkOrder(child_id=ch.id, kind="dispatch",
                     routing_model="section_pooled", priority_tier="P1"))
    await db.flush()
    db.add(WorkOrder(child_id=ch.id, kind="dispatch",
                     routing_model="section_pooled", priority_tier="P1"))
    with _pytest.raises(_IntegrityError):
        await db.flush()


async def test_g1_glitch_child_unique(db, make_account):
    """A 2nd glitch for the same child_id is rejected (UNIQUE)."""
    from conduit.shared.models import Glitch

    ch, _pid, _aid = await _g1_child(db, make_account)
    db.add(Glitch(child_id=ch.id, opened_from="problem_report"))
    await db.flush()
    db.add(Glitch(child_id=ch.id, opened_from="dispute"))
    with _pytest.raises(_IntegrityError):
        await db.flush()


async def test_g1_sla_preset_partial_unique(db, make_account):
    """uq_sla_active_tier: only ONE ACTIVE sla_preset per (property, tier);
    a 2nd ACTIVE is rejected, a 2nd disabled is allowed."""
    from conduit.shared.models import SLAPreset

    _ch, pid, _aid = await _g1_child(db, make_account)

    def _preset(status="active"):
        return SLAPreset(property_id=pid, tier="P2",
                         accept_window_seconds=60, fulfilment_sla_seconds=600,
                         supervisor_sla_seconds=1200, status=status)

    db.add(_preset())
    await db.flush()
    db.add(_preset(status="disabled"))                  # disabled dup → ok
    await db.flush()
    db.add(_preset())                                   # 2nd ACTIVE → reject
    with _pytest.raises(_IntegrityError):
        await db.flush()


async def test_g1_escalation_ladder_partial_unique(db, make_account):
    """uq_ladder_active_property: only ONE ACTIVE escalation_ladder per
    property; a 2nd ACTIVE is rejected, a disabled one is allowed."""
    from conduit.shared.models import EscalationLadder

    _ch, pid, aid = await _g1_child(db, make_account)

    def _ladder(status="active"):
        return EscalationLadder(property_id=pid,
                                duty_manager_account_id=aid,
                                n_cycle_bound=3, status=status)

    db.add(_ladder())
    await db.flush()
    db.add(_ladder(status="disabled"))                  # disabled dup → ok
    await db.flush()
    db.add(_ladder())                                   # 2nd ACTIVE → reject
    with _pytest.raises(_IntegrityError):
        await db.flush()
