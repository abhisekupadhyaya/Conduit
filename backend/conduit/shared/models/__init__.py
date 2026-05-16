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

__all__ = ["Base"]
