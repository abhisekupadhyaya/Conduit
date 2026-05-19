from conduit.shared.integrations import openai as llm
from conduit.guest.services import intake


# Task 13 enable: skip removed; ``monkeypatch_all`` added to the signature so
# the conftest-provided helper (which the verbatim body invokes by bare name)
# resolves as a fixture. Body/assertions otherwise unchanged.
async def test_grounded_answer_then_close(db, make_account, login,
                                          seeded_guest_with_stay,
                                          monkeypatch_all):
    actor, ambient = seeded_guest_with_stay      # fixture (Task 13)
    async def fclassify(t, c):
        return [{"text": t, "issue_code": "INFO_DINING",
                 "fulfilment_mode": "no_dispatch", "outcome": "no_dispatch",
                 "is_problem_report": False}]
    async def fground(q, ctx):
        return {"grounded": True, "leaves_no_dispatch": False,
                "answer": "7-10:30 Atrium", "used_kb_ids": [],
                "used_fields": ["room_label"]}
    monkeypatch_all(llm, fclassify, fground)     # helper sets llm.classify/ground
    out = await intake.submit_request(db, actor, "what time is breakfast?")
    await db.flush()
    assert out["children"][0]["terminal"] == "answered"
    assert "7-10:30" in out["children"][0]["answer"]


async def test_multi_intent_fans_into_independent_children(
        db, seeded_guest_with_stay, fake_decompose, fake_llm):
    fake_decompose["texts"] = ["extra towels", "what time is checkout"]
    async def fc(t, cat, history=""):
        code = "HK_REQUEST" if "towel" in t else "INFO_GENERAL"
        mode = "dispatch" if "towel" in t else "no_dispatch"
        return [{"text": t, "issue_code": code, "fulfilment_mode": mode,
                 "outcome": "auto" if "towel" in t else "no_dispatch",
                 "is_problem_report": False}]
    async def fg(q, ctx, history=""):
        return {"grounded": True, "leaves_no_dispatch": False,
                "answer": "11am", "used_kb_ids": [], "used_fields": []}
    fake_llm["classify"] = fc; fake_llm["ground"] = fg
    actor, _ = seeded_guest_with_stay
    from conduit.guest.services import intake
    out = await intake.submit_request(db, actor, "towels and checkout time?")
    await db.flush()
    assert out["split"] is True
    assert len(out["children"]) == 2
    assert {c["text"] for c in out["children"]} == {
        "extra towels", "what time is checkout"}


async def test_single_need_is_instant_ack_not_split(
        db, seeded_guest_with_stay, fake_decompose, fake_llm):
    async def fc(t, cat, history=""):
        return [{"text": t, "issue_code": "HK_REQUEST",
                 "fulfilment_mode": "dispatch", "outcome": "auto",
                 "is_problem_report": False}]
    fake_llm["classify"] = fc
    actor, _ = seeded_guest_with_stay
    from conduit.guest.services import intake
    out = await intake.submit_request(db, actor, "extra towels")
    await db.flush()
    assert out["split"] is False and len(out["children"]) == 1
