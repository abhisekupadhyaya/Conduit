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


# --- Code-review regression locks (Important #1/#2, Minor #3) ----------------

def test_triage_checkout_info_question_is_not_a_mutation_flag():
    # spec §9.2: the canonical "checkout?" child is a no-dispatch info
    # question, NOT a reservation/revenue mutation. triage emits only
    # AUTO/CLARIFY/FLAG (no-dispatch routing is decided elsewhere by
    # issue-code), so a complete low-risk info question ⇒ AUTO.
    assert triage.triage("what time is checkout?").outcome == \
        triage.TriageOutcome.AUTO
    assert triage.triage("what time is checkout").outcome == \
        triage.TriageOutcome.AUTO


def test_triage_genuine_late_checkout_mutation_still_flags():
    # D24 / §7.2: a genuine reservation-mutation phrase still FLAGs.
    assert triage.triage("I want a late checkout").outcome == \
        triage.TriageOutcome.FLAG
    assert triage.triage("please extend my stay").outcome == \
        triage.TriageOutcome.FLAG


def test_triage_word_boundary_does_not_false_flag_charger():
    # 'charge' is a substring of 'charger' but not a word-boundary hit.
    assert triage.triage("my phone charger is missing").outcome == \
        triage.TriageOutcome.AUTO
    assert triage.triage("please bring me a charger").outcome == \
        triage.TriageOutcome.AUTO


def test_triage_word_boundary_does_not_false_flag_fireplace():
    # 'fire' is a substring of 'fireplace' but not a word-boundary hit.
    assert triage.triage("fireplace instructions please").outcome == \
        triage.TriageOutcome.AUTO


def test_triage_real_fire_still_flags():
    # Positive safety check: a true fire hazard still FLAGs (D30).
    assert triage.triage("there is a fire in my room").outcome == \
        triage.TriageOutcome.FLAG
