# tests/binding/test_models.py
def test_models_import_and_columns():
    from conduit.shared.models.property import Property
    from conduit.shared.models.section import Section
    from conduit.shared.models.room import Room
    from conduit.shared.models.stay import Stay
    from conduit.shared.models.event import (
        Event, EventStayCreated, EventStayEnded, EventGuestRelocated,
    )
    assert {"id", "name"} <= set(Property.__table__.columns.keys())
    assert {"id", "property_id", "label"} <= set(
        Section.__table__.columns.keys())
    assert {"id", "section_id", "label"} <= set(Room.__table__.columns.keys())
    assert {"id", "guest_account_id", "room_id", "check_in", "check_out",
            "status"} <= set(Stay.__table__.columns.keys())
    assert {"id", "type", "actor_account_id", "at"} <= set(
        Event.__table__.columns.keys())
    relfks = {fk.column.table.name
              for fk in EventGuestRelocated.__table__.foreign_keys}
    assert {"event", "stay", "room"} <= relfks
    assert "section" in {fk.column.table.name
                         for fk in Room.__table__.foreign_keys}
    assert {"account", "room"} <= {fk.column.table.name
                                   for fk in Stay.__table__.foreign_keys}
