"""Regression guard: the LLM structured-output schema MUST constrain the
enum-valued fields, so the model cannot return free text that later blows up
TriageOutcome() and gets silently swallowed by the degrade path.

This is DB-free and network-free on purpose: the FakeLLM test bench cannot
catch a real-model/schema mismatch, so this asserts the schema contract
directly. Fails on the old `outcome: str`; passes once it is a Literal.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from conduit.shared.integrations.openai import _Child


def test_child_outcome_is_constrained_to_enum():
    # A valid value parses.
    ok = _Child(text="x", issue_code="INFO_DINING",
                fulfilment_mode="no_dispatch", outcome="no_dispatch",
                is_problem_report=False)
    assert ok.outcome == "no_dispatch"

    # A free-text description (what gpt-5.4-mini actually returned in the
    # field bug) MUST be rejected at the schema boundary.
    with pytest.raises(ValidationError):
        _Child(text="x", issue_code="INFO_DINING",
               fulfilment_mode="no_dispatch",
               outcome="Asks for dining breakfast hours",
               is_problem_report=False)


def test_child_fulfilment_mode_is_constrained():
    with pytest.raises(ValidationError):
        _Child(text="x", issue_code=None, fulfilment_mode="maybe",
               outcome="clarify", is_problem_report=False)
