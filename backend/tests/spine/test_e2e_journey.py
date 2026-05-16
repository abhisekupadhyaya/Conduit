"""End-to-end no-dispatch journey sentinel (Spec §11).

ONE scripted test that *is* the slice: supervisor authors+edits a code & KB
entry, a guest walks the full no-dispatch conversation (grounded answer →
closure-lite → ungroundable deferral → live-policy disable → mixed multi-intent
→ LLM-down degrade), and every load-bearing invariant is asserted against the
real event/detail rows. Deterministic: the only non-determinism source (the
LLM) is replaced by the ``fake_llm`` fixture; no network, no sleep.

How the guest is driven
-----------------------
``seeded_guest_with_stay`` builds the guest via ``make_account("guest", ...)``
with the conftest default password ``"pw-123456"``; the guest's username is
recoverable as ``actor.username``. The supervisor CRUD and the final
LLM-down "guest never gets a 5xx" assertion are therefore driven over HTTP
through the merged per-test ``client`` (its ``db_session`` override yields the
SAME savepoint ``db`` the service runs on — proven by
``test_structural_guards.py::test_live_policy_disable``). ``login`` swaps the
one active session cookie, so we log in as the supervisor for supervisor calls
and re-log-in as the guest for the HTTP guest call. The remaining guest
journey phases (B–F) are driven through the ``intake`` service directly —
exactly the proven pattern in ``test_live_policy_disable`` /
``test_one_event_per_transition`` — because that gives the deterministic
return dicts and direct event-row access the per-phase invariants need.

Exact-count strategy under one savepoint
----------------------------------------
It is ONE test ⇒ ONE savepoint ⇒ rows from earlier phases persist within the
test. Every count assertion is therefore SCOPED to the freshly-returned
identifiers of the phase under test: ``request_created`` is filtered by
``EventRequestCreated.request_id == <this phase's request id>`` and child
events are filtered by the detail table's ``child_id == <this phase's child
id>``. That makes each assertion exactly 1 (or 0) regardless of how many
prior phases ran — robust, not flaky.
"""
from __future__ import annotations

import uuid

import sqlalchemy as sa

from conduit.guest.services import intake
from conduit.shared.integrations.openai import LLMUnavailable
from conduit.shared.models import (
    ChildSubRequest,
    Event,
    EventChildAnswered,
    EventChildClosed,
    EventChildDeferred,
    EventChildParked,
    EventChildTriaged,
    EventRequestCreated,
    NoDispatchResolution,
    Request,
)

_GUEST_PW = "pw-123456"  # conftest default in make_account / seeded_guest


async def _events_of_type_for_child(db, detail_cls, child_id):
    """Events of a given child-detail type scoped to one child_id."""
    rows = (await db.execute(
        sa.select(detail_cls).where(detail_cls.child_id == child_id)
    )).scalars().all()
    return rows


async def test_e2e_no_dispatch_journey(client, make_account, login, db,
                                       fake_llm, seeded_guest_with_stay):
    actor, ambient = seeded_guest_with_stay

    # ---- A. Supervisor creates + edits a code & a KB entry (HTTP) ---------
    await make_account("supervisor", "sup", _GUEST_PW)
    await login("sup", _GUEST_PW)

    rc = await client.post("/api/supervisor/issue-codes", json={
        "code": "INFO_DINING", "label": "Dining", "department": "concierge",
        "fulfilment_mode": "no_dispatch", "routing_model": "none",
        "intent_kind": "service"})
    assert rc.status_code == 201, rc.text
    code_id = rc.json()["id"]
    # Edit the code (exercise "creates + edits a code").
    rce = await client.patch(f"/api/supervisor/issue-codes/{code_id}",
                             json={"label": "Dining & hours"})
    assert rce.status_code == 200 and rce.json()["label"] == "Dining & hours"

    rk = await client.post("/api/supervisor/kb", json={
        "topic": "breakfast", "content": "breakfast is served 7-10:30"})
    assert rk.status_code == 201, rk.text
    kb_id = rk.json()["id"]
    # Edit the KB entry (exercise "creates + edits a KB entry").
    rke = await client.patch(f"/api/supervisor/kb/{kb_id}",
                             json={"content": "breakfast is 7-10:30 in Atrium"})
    assert rke.status_code == 200
    assert "Atrium" in rke.json()["content"]

    # ---- B. Grounded happy path ------------------------------------------
    async def fclassify_one(t, cat):
        return [{"text": t, "issue_code": "INFO_DINING",
                 "fulfilment_mode": "no_dispatch", "outcome": "no_dispatch",
                 "is_problem_report": False}]

    async def fground_yes(q, ctx):
        return {"grounded": True, "leaves_no_dispatch": False,
                "answer": "Breakfast 7-10:30", "used_kb_ids": [],
                "used_fields": ["room_label"]}

    fake_llm["classify"] = fclassify_one
    fake_llm["ground"] = fground_yes

    out_b = await intake.submit_request(db, actor, "what time is breakfast?")
    await db.flush()
    req_b = uuid.UUID(out_b["request_id"])
    child_b = uuid.UUID(out_b["children"][0]["child_id"])
    assert out_b["children"][0]["terminal"] == "answered"
    assert "7-10:30" in out_b["children"][0]["answer"]

    # Exactly one request_created (scoped to THIS request) + detail row.
    rc_evs = (await db.execute(sa.select(EventRequestCreated).where(
        EventRequestCreated.request_id == req_b))).scalars().all()
    assert len(rc_evs) == 1
    assert (await db.execute(sa.select(Event).where(
        Event.id == rc_evs[0].event_id,
        Event.type == "request_created"))).scalar_one()
    # Exactly one child_triaged + one child_answered for THIS child.
    tri = await _events_of_type_for_child(db, EventChildTriaged, child_b)
    assert len(tri) == 1
    ans = await _events_of_type_for_child(db, EventChildAnswered, child_b)
    assert len(ans) == 1
    assert ans[0].resolution_child_id == child_b
    res_b = await db.get(NoDispatchResolution, child_b)
    assert res_b is not None and res_b.mode == "grounded_answer"
    assert res_b.answer_text == "Breakfast 7-10:30"

    # ---- C. Closure-lite "yes" → closed ----------------------------------
    conf = await intake.confirm(db, actor, child_b, True)
    await db.flush()
    assert conf["state"] == "closed"
    child_b_row = await db.get(ChildSubRequest, child_b)
    assert child_b_row.state == "closed"
    closed = await _events_of_type_for_child(db, EventChildClosed, child_b)
    assert len(closed) == 1
    res_b_after = await db.get(NoDispatchResolution, child_b)
    assert res_b_after.helpful == "yes"

    # ---- D. Ungroundable deferral ----------------------------------------
    async def fground_no(q, ctx):
        return {"grounded": False, "leaves_no_dispatch": False, "answer": "",
                "used_kb_ids": [], "used_fields": []}

    fake_llm["ground"] = fground_no
    out_d = await intake.submit_request(db, actor, "is there a helipad?")
    await db.flush()
    child_d = uuid.UUID(out_d["children"][0]["child_id"])
    assert out_d["children"][0]["terminal"] == "logged"
    child_d_row = await db.get(ChildSubRequest, child_d)
    assert child_d_row.state == "concierge_queue"
    def_d = await _events_of_type_for_child(db, EventChildDeferred, child_d)
    assert len(def_d) == 1
    res_d = await db.get(NoDispatchResolution, child_d)
    assert res_d is not None and res_d.mode == "human_deferral"

    # ---- E. Live policy: disable the KB entry, still defers ---------------
    await login("sup", _GUEST_PW)  # cookie is still supervisor's, but be explicit
    rkd = await client.patch(f"/api/supervisor/kb/{kb_id}",
                             json={"status": "disabled"})
    assert rkd.status_code == 200 and rkd.json()["status"] == "disabled"

    captured: dict[str, str] = {}

    async def fground_no_capture(q, ctx):
        captured["ctx"] = ctx
        return {"grounded": False, "leaves_no_dispatch": False, "answer": "",
                "used_kb_ids": [], "used_fields": []}

    fake_llm["classify"] = fclassify_one
    fake_llm["ground"] = fground_no_capture
    out_e = await intake.submit_request(db, actor, "what time is breakfast?")
    await db.flush()
    child_e = uuid.UUID(out_e["children"][0]["child_id"])
    assert out_e["children"][0]["terminal"] == "logged"  # still defers
    child_e_row = await db.get(ChildSubRequest, child_e)
    assert child_e_row.state == "concierge_queue"
    # The disabled KB entry is excluded from the LIVE grounding context.
    assert "breakfast is 7-10:30 in Atrium" not in captured["ctx"]
    assert "breakfast" not in captured["ctx"].split("Knowledge base:")[-1]

    # ---- F. Mixed multi-intent: independent fates ------------------------
    async def fclassify_two(t, cat):
        return [
            {"text": "what time is breakfast?", "issue_code": "INFO_DINING",
             "fulfilment_mode": "no_dispatch", "outcome": "no_dispatch",
             "is_problem_report": False},
            {"text": "send extra towels", "issue_code": None,
             "fulfilment_mode": None, "outcome": "auto",
             "is_problem_report": False},
        ]

    fake_llm["classify"] = fclassify_two
    fake_llm["ground"] = fground_yes
    out_f = await intake.submit_request(
        db, actor, "what time is breakfast? also send extra towels")
    await db.flush()
    assert len(out_f["children"]) == 2
    c0 = out_f["children"][0]
    c1 = out_f["children"][1]
    assert c0["terminal"] == "answered"   # no_dispatch child got grounded
    assert c1["terminal"] == "logged"     # auto child parked
    child_f0 = uuid.UUID(c0["child_id"])
    child_f1 = uuid.UUID(c1["child_id"])
    assert child_f0 != child_f1
    # Independent fates: f0 answered (resolution), f1 parked (event, no res).
    res_f0 = await db.get(NoDispatchResolution, child_f0)
    assert res_f0 is not None and res_f0.mode == "grounded_answer"
    assert (await db.get(NoDispatchResolution, child_f1)) is None
    parked_f1 = await _events_of_type_for_child(db, EventChildParked, child_f1)
    assert len(parked_f1) == 1
    # Both children persisted with their own states.
    assert (await db.get(ChildSubRequest, child_f0)).state == "answered"
    f1_row = await db.get(ChildSubRequest, child_f1)
    assert f1_row.state == "triaged" and f1_row.outcome == "auto"

    # ---- G. LLM down: guest never gets a 5xx (HTTP) ----------------------
    async def fclassify_down(t, cat):
        raise LLMUnavailable("down")

    fake_llm["classify"] = fclassify_down
    fake_llm["ground"] = fground_yes  # unreachable; classify fails first

    await login(actor.username, _GUEST_PW)  # swap cookie back to the guest
    rg = await client.post("/api/guest/requests",
                           json={"text": "anything at all"})
    assert rg.status_code == 200, rg.text  # NOT 5xx — degrade, never crash
    body = rg.json()
    assert len(body["children"]) == 1
    g_child = body["children"][0]
    assert g_child["terminal"] == "logged"  # degraded (parked, uncategorized)
    req_g = uuid.UUID(body["request_id"])
    child_g = uuid.UUID(g_child["child_id"])
    # The child is uncategorized (no code mapped) and parked, not dropped.
    g_row = await db.get(ChildSubRequest, child_g)
    assert g_row.uncategorized is True
    g_parked = await _events_of_type_for_child(db, EventChildParked, child_g)
    assert len(g_parked) == 1
    # request_created still persisted — nothing was silently dropped.
    rc_g = (await db.execute(sa.select(EventRequestCreated).where(
        EventRequestCreated.request_id == req_g))).scalars().all()
    assert len(rc_g) == 1
    assert (await db.get(Request, req_g)) is not None
