"""ORM models — the SPINE/CONFIG/IDENTITY entities.

Concrete tables are defined here as the data model hardens. The shapes and
their rationale live in docs/datamodels/ (schema-draft.md + the firm-vs-soft
split). Deliberately empty in scaffolding — the data model is marked
"subject to change" and is hardened in the build phase, not guessed here.

Firm-first order to implement (per schema-draft "Firm" list):
  1. event            (append-only — every consumer reads this)
  2. timer            (the engine depends on it; AD5)
  3. request / child_sub_request (the unit; D35)
"""
from __future__ import annotations

from conduit.shared.db import Base
from conduit.shared.models.account import Account
from conduit.shared.models.property import Property
from conduit.shared.models.section import Section
from conduit.shared.models.room import Room
from conduit.shared.models.stay import Stay
from conduit.shared.models.event import (
    Event, EventStayCreated, EventStayEnded, EventGuestRelocated,
)

__all__ = ["Base", "Account", "Property", "Section", "Room", "Stay",
           "Event", "EventStayCreated", "EventStayEnded",
           "EventGuestRelocated"]
