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


async def test_decompose_single_need_returns_one(monkeypatch):
    async def fake(t): return [t]
    monkeypatch.setattr(llm, "decompose", fake)
    assert await triage.decompose("can I get extra towels") == \
        ["can I get extra towels"]


async def test_decompose_multi_need_returns_n(monkeypatch):
    async def fake(t):
        return ["extra towels", "the TV is broken", "what time is checkout"]
    monkeypatch.setattr(llm, "decompose", fake)
    out = await triage.decompose(
        "towels, the TV is broken, and what time is checkout?")
    assert out == ["extra towels", "the TV is broken", "what time is checkout"]


async def test_decompose_empty_or_garbage_never_zero(monkeypatch):
    async def fake(t): return []
    monkeypatch.setattr(llm, "decompose", fake)
    out = await triage.decompose("zzz")
    assert out == ["zzz"]                       # never 0; never a silent drop


async def test_decompose_llm_unavailable_falls_back_to_single(monkeypatch):
    async def boom(t): raise llm.LLMUnavailable("down")
    monkeypatch.setattr(llm, "decompose", boom)
    out = await triage.decompose("a and b")
    assert out == ["a and b"]                   # AD11 conservative single text


def test_triage_complete_low_risk_auto():
    r = triage.triage("2 extra bath towels to my room")
    assert r.outcome == triage.TriageOutcome.AUTO


def test_triage_missing_slot_clarifies():
    r = triage.triage("I need something")
    assert r.outcome == triage.TriageOutcome.CLARIFY


def test_triage_d30_risk_flags():
    r = triage.triage("there is water flooding the bathroom, urgent")
    assert r.outcome == triage.TriageOutcome.FLAG


def test_triage_tier_not_from_asserted_urgency():
    a = triage.triage("extra towels")
    b = triage.triage("URGENT!!! extra towels NOW")
    assert a.outcome == b.outcome            # D20: urgency ≠ outcome/tier
