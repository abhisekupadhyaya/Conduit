# tests/binding/test_exceptions.py
from conduit.core.exceptions import ValidationError, ConduitError


def test_validation_error_is_422_conduit_error():
    e = ValidationError("bad")
    assert isinstance(e, ConduitError)
    assert e.status_code == 422
    assert e.message == "bad"
