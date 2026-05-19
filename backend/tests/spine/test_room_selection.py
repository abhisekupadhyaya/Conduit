from conduit.shared.domain import room_selection as rs


def test_excludes_occupied_and_current_deterministic():
    rooms = [("r1", "101"), ("r2", "102"), ("r3", "103")]
    occupied = {"r2"}
    rec, elig = rs.select(rooms=rooms, occupied_room_ids=occupied,
                          current_room_id="r1")
    assert "r1" not in elig and "r2" not in elig
    assert elig == ["r3"] and rec == "r3"


def test_empty_when_none_available():
    rec, elig = rs.select(rooms=[("r1", "101")], occupied_room_ids=set(),
                          current_room_id="r1")
    assert rec is None and elig == []


def test_order_preserved_across_multiple_eligible():
    # §7.1 invariant: eligible follows caller-supplied order verbatim
    # (no sorting/shuffling); recommended = the FIRST eligible.
    rooms = [("r5", "205"), ("r1", "201"), ("r9", "209"), ("r3", "203")]
    rec, elig = rs.select(rooms=rooms, occupied_room_ids={"r9"},
                          current_room_id="r1")
    assert elig == ["r5", "r3"] and rec == "r5"


def test_current_room_absent_from_rooms_still_excluded():
    # §7.1 invariant: current is excluded even if it never appears in
    # ``rooms``; selection still yields the deterministic available set.
    rooms = [("r1", "101"), ("r2", "102")]
    rec, elig = rs.select(rooms=rooms, occupied_room_ids=set(),
                          current_room_id="rX")
    assert elig == ["r1", "r2"] and rec == "r1"
