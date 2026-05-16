# tests/binding/test_schemas.py
import pytest, pydantic
from conduit.supervisor.schemas.binding import SectionOut


def test_section_out_forbids_extra():
    with pytest.raises(pydantic.ValidationError):
        SectionOut(id="00000000-0000-0000-0000-000000000000", label="N",
                   room_count=0, created_at="2026-01-01T00:00:00Z", x=1)
