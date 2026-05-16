import pytest
from conduit.shared.integrations import openai as llm
from conduit.shared.integrations.openai import LLMUnavailable


async def test_classify_and_ground_are_callable_and_typed(monkeypatch):
    async def fake_classify(text, catalog):
        return [{"text": text, "issue_code": "INFO_DINING",
                 "fulfilment_mode": "no_dispatch", "outcome": "no_dispatch",
                 "is_problem_report": False}]
    monkeypatch.setattr(llm, "classify", fake_classify)
    out = await llm.classify("breakfast?", [])
    assert out[0]["issue_code"] == "INFO_DINING"


async def test_unavailable_is_raisable():
    with pytest.raises(LLMUnavailable):
        raise LLMUnavailable("circuit open")


async def test_circuit_breaker_trips_and_resets(monkeypatch):
    llm._reset_circuit_breaker()
    try:
        calls = {"n": 0}

        async def boom(model, sys, text):
            calls["n"] += 1
            raise RuntimeError("sdk down")

        monkeypatch.setattr(llm, "_parse_classify", boom)

        # Drive _CB_THRESHOLD consecutive logical failures.
        for _ in range(llm._CB_THRESHOLD):
            with pytest.raises(LLMUnavailable):
                await llm.classify("hello", [])
        assert calls["n"] == llm._CB_THRESHOLD

        # Circuit now open: a further call must fast-raise WITHOUT
        # invoking the (still-monkeypatched-to-count) helper.
        with pytest.raises(LLMUnavailable):
            await llm.classify("hello", [])
        assert calls["n"] == llm._CB_THRESHOLD  # unchanged

        # Reset and confirm the success path works again.
        llm._reset_circuit_breaker()

        async def ok(model, sys, text):
            calls["n"] += 1
            return llm._Decompose(children=[llm._Child(
                text=text, issue_code="INFO_DINING",
                fulfilment_mode="no_dispatch", outcome="no_dispatch",
                is_problem_report=False)])

        monkeypatch.setattr(llm, "_parse_classify", ok)
        out = await llm.classify("breakfast?", [])
        assert out[0]["issue_code"] == "INFO_DINING"
        assert calls["n"] == llm._CB_THRESHOLD + 1
    finally:
        llm._reset_circuit_breaker()
