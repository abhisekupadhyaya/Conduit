from conduit.shared.domain.conversation import Turn, window


def test_empty_yields_empty_string():
    assert window([], limit=50) == ""


def test_orders_and_labels_roles():
    turns = [Turn(role="guest", text="what time is checkout?"),
             Turn(role="system", text="11am")]
    assert window(turns, limit=50) == "guest: what time is checkout?\nsystem: 11am"


def test_sliding_keeps_only_last_n_oldest_dropped():
    turns = [Turn(role="guest", text=f"m{i}") for i in range(60)]
    out = window(turns, limit=50)
    lines = out.split("\n")
    assert len(lines) == 50
    assert lines[0] == "guest: m10"      # oldest 10 dropped
    assert lines[-1] == "guest: m59"


def test_pure_no_io():
    # Constructed from plain values; importing/calling touches no DB/session.
    import inspect
    import conduit.shared.domain.conversation as m
    src = inspect.getsource(m)
    assert "AsyncSession" not in src and "select(" not in src
