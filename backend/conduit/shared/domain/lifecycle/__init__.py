"""Lifecycle package — per-entity pure state machines + back-compat facade.

C3 converts the single-file ``lifecycle.py`` into this package. Each entity
(child / workorder / escalation / glitch) is a PURE submodule exposing a
``_LEGAL: dict[str, set[str]]`` and ``legal(frm, to) -> bool``. No DB, no I/O.

Back-compat is mandatory. The merged consumers
(``conduit.guest.services.intake / nodispatch / smalltalk`` and
``tests/spine/test_lifecycle.py``) do
``from conduit.shared.domain import lifecycle`` then call
``lifecycle.transition`` / ``lifecycle.ChildState``. Those names are
re-exported here unchanged so behaviour is identical. The child ``_LEGAL``
moved into ``child.py`` is a *superset* of the old map (additive union with
the dispatch arc), so every previously-legal transition stays legal.

The orchestrator ``transition()`` is intentionally still the merged
single-entity child implementation — the C4 task replaces/expands it. C3
only adds the per-entity machines + the package conversion (YAGNI).
"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from conduit.core.exceptions import ConflictError
from conduit.shared.events import writer

from . import child as child
from . import escalation as escalation
from . import glitch as glitch
from . import workorder as workorder
from .child import ChildState as ChildState

# Preserved from the merged ``lifecycle.py`` for the child orchestrator
# back-compat (intake/nodispatch/smalltalk + test_lifecycle.py). The legal
# map is sourced from the moved child machine (superset of the old map).
_LEGAL = child._LEGAL
_EVENT = {
    "triaged": "child_triaged",
    "answered": "child_answered",
    "concierge_queue": "child_deferred",
    "closed": "child_closed",
    "reopened": "child_reopened",
}

__all__ = [
    "ChildState",
    "child",
    "workorder",
    "escalation",
    "glitch",
    "transition",
]


async def transition(s: AsyncSession, child, to: str, *,
                      actor_account_id=None, resolution_child_id=None) -> None:
    """Apply a guarded child transition and append the corresponding event
    (conduit.shared.events) in the same transaction (AD5).

    Unchanged from the merged ``lifecycle.py`` — the per-entity machines added
    in C3 do not alter this behaviour; the C4 task owns the orchestrator.
    """
    if to not in _LEGAL.get(child.state, set()):
        raise ConflictError(f"illegal transition {child.state}->{to}")
    child.state = to
    s.add(child)
    await writer.emit_child(s, _EVENT[to], child.id, actor_account_id,
                            resolution_child_id=resolution_child_id)
