import inspect
import pytest
from conduit.shared.domain import grounding
from conduit.shared.integrations import openai as llm


def test_ground_accepts_history_kw():
    assert "history" in inspect.signature(grounding.ground).parameters


@pytest.mark.asyncio
async def test_history_is_forwarded(monkeypatch):
    seen = {}
    async def fake(q, ctx, history=""):
        seen["history"] = history
        return {"grounded": True, "leaves_no_dispatch": False,
                "answer": "ok", "used_kb_ids": [], "used_fields": []}
    monkeypatch.setattr(llm, "ground", fake)
    await grounding.ground("q?", kb=[], facts={
        "room_label": "1", "section_label": "A", "check_in": "x",
        "check_out": "y", "stay_status": "active"}, history="H")
    assert seen["history"] == "H"
