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
