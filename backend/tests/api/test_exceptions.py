def test_conflict_error_is_409():
    from conduit.core.exceptions import ConflictError, ConduitError
    e = ConflictError("dupe")
    assert isinstance(e, ConduitError)
    assert e.status_code == 409
    assert e.message == "dupe"
