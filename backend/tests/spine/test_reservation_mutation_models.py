# backend/tests/spine/test_reservation_mutation_models.py
from conduit.shared import models as m


def test_rec_apply_reservation_mutation_exported_and_shaped():
    cls = m.RecApplyReservationMutation
    cols = cls.__table__.columns
    assert cls.__tablename__ == "rec_apply_reservation_mutation"
    assert "recommendation_escalation_id" in cols
    assert "field" in cols and "requested_value" in cols


def test_ck_rec_action_widened():
    rec = m.Recommendation
    ck = next(c for c in rec.__table__.constraints
              if getattr(c, "name", "") == "ck_rec_action")
    assert "apply_reservation_mutation" in str(ck.sqltext)


def test_event_reservation_mutated_shaped():
    cls = m.EventReservationMutated
    cols = cls.__table__.columns
    assert cls.__tablename__ == "event_reservation_mutated"
    for c in ("event_id", "stay_id", "field", "old_value", "new_value"):
        assert c in cols


def test_ck_event_type_widened():
    ev = m.Event
    ck = next(c for c in ev.__table__.constraints
              if getattr(c, "name", "") == "ck_event_type")
    assert "reservation_mutated" in str(ck.sqltext)


def test_child_has_requested_checkout_nullable():
    col = m.ChildSubRequest.__table__.columns["requested_checkout"]
    assert col.nullable is True


def test_ndr_mode_widened():
    ck = next(c for c in m.NoDispatchResolution.__table__.constraints
              if getattr(c, "name", "") == "ck_ndr_mode")
    assert "reservation_mutation" in str(ck.sqltext)
