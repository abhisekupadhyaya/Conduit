from conduit.shared.domain import triage
from conduit.shared.integrations import openai as llm


async def test_mutation_code_forces_flag(monkeypatch):
    catalog = [{"code": "RES_MUTATION", "label": "x", "fulfilment_mode":
                "no_dispatch", "is_reservation_mutation": True}]

    async def fake(text, cat):
        return [{"text": text, "issue_code": "RES_MUTATION",
                 "fulfilment_mode": "no_dispatch", "outcome": "no_dispatch",
                 "is_problem_report": False}]

    monkeypatch.setattr(llm, "classify", fake)
    out = await triage.classify("can I check out at 2pm?", catalog)
    assert out[0].outcome == "flag"          # forced, LLM said no_dispatch


async def test_unknown_code_is_uncategorized(monkeypatch):
    async def fake(text, cat):
        return [{"text": text, "issue_code": None, "fulfilment_mode": None,
                 "outcome": "clarify", "is_problem_report": False}]

    monkeypatch.setattr(llm, "classify", fake)
    out = await triage.classify("zzz", [])
    assert out[0].uncategorized is True and out[0].outcome == "clarify"
