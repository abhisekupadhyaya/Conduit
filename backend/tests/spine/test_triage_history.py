import datetime as dt
import pytest
from conduit.shared.domain import triage
from conduit.shared.integrations import openai as llm


CATALOG = [{"code": "LATE_CHECKOUT", "label": "Late checkout",
            "fulfilment_mode": "no_dispatch", "is_reservation_mutation": True}]


@pytest.mark.asyncio
async def test_history_does_not_change_outcome_only_extraction(monkeypatch):
    async def fake(text, catalog, history=""):
        return [{"text": text, "issue_code": "LATE_CHECKOUT",
                 "fulfilment_mode": "no_dispatch", "outcome": "no_dispatch",
                 "is_problem_report": False,
                 "requested_checkout": "2026-05-16T14:00:00+00:00"}]
    monkeypatch.setattr(llm, "classify", fake)

    no_hist = await triage.classify("till 2pm?", CATALOG)
    with_hist = await triage.classify("till 2pm?", CATALOG,
                                      history="guest: checkout?\nsystem: 11am")
    # Resolution A forces flag for a mutation code REGARDLESS of history:
    assert no_hist[0].outcome.value == "flag"
    assert with_hist[0].outcome.value == "flag"
    # Extraction carried through:
    assert with_hist[0].requested_checkout == dt.datetime(
        2026, 5, 16, 14, 0, tzinfo=dt.timezone.utc)


@pytest.mark.asyncio
async def test_bad_iso_is_conservative_none(monkeypatch):
    async def fake(text, catalog, history=""):
        return [{"text": text, "issue_code": "LATE_CHECKOUT",
                 "fulfilment_mode": "no_dispatch", "outcome": "no_dispatch",
                 "is_problem_report": False,
                 "requested_checkout": "not-a-date"}]
    monkeypatch.setattr(llm, "classify", fake)
    out = await triage.classify("x", CATALOG)
    assert out[0].requested_checkout is None   # never crash on LLM noise
