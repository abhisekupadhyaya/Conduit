import datetime as dt

from conduit.shared.engine import spine
from conduit.shared.models import RecApplyReservationMutation


def test_rec_detail_map_has_mutation():
    eid = __import__("uuid").uuid4()
    when = dt.datetime(2026, 5, 16, 14, 0, tzinfo=dt.timezone.utc)
    obj = spine._REC_DETAIL["apply_reservation_mutation"](
        eid, {"field": "check_out", "requested_value": when})
    assert isinstance(obj, RecApplyReservationMutation)
    assert obj.field == "check_out" and obj.requested_value == when
