import inspect
from conduit.shared.integrations import openai as llm


def test_classify_and_ground_accept_history_kw():
    assert "history" in inspect.signature(llm.classify).parameters
    assert "history" in inspect.signature(llm.ground).parameters


def test_child_schema_has_requested_checkout():
    assert "requested_checkout" in llm._Child.model_fields
