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
