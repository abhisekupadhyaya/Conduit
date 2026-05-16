from conduit.shared.domain import grounding
from conduit.shared.integrations import openai as llm


async def test_ground_builds_context_and_returns(monkeypatch):
    captured = {}

    async def fake(q, ctx):
        captured["ctx"] = ctx
        return {"grounded": True, "leaves_no_dispatch": False,
                "answer": "7-10:30", "used_kb_ids": ["k1"],
                "used_fields": ["room_label"]}

    monkeypatch.setattr(llm, "ground", fake)
    res = await grounding.ground(
        "breakfast?",
        kb=[{"id": "k1", "topic": "breakfast", "content": "7-10:30"}],
        facts={"room_label": "412", "section_label": "A",
               "check_in": "2026-05-16", "check_out": "2026-05-18",
               "stay_status": "active"})
    assert res["grounded"] is True
    assert "breakfast" in captured["ctx"] and "412" in captured["ctx"]
