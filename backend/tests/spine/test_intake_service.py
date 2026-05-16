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
