"""Conversation window — pure cross-portal domain (Spec §7.1).

Extraction-only (D5/D30): the bounded last-N transcript is prompt context
for the LLM's extraction; it never feeds the deterministic risk rulebook.
PURE: no DB, no session, no clock — the caller does the time-ordered read
(``rdal``/``cdal``/``resdal``) and hands rows in. Mirrors grounding.py:
"the DB read belongs to the caller, never here".
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Turn:
    role: str          # "guest" | "system"
    text: str


def window(turns: list[Turn], *, limit: int) -> str:
    """The last ``limit`` turns, chronological, role-labelled, oldest
    dropped past the bound. ``turns`` MUST already be time-ordered ascending
    by the caller."""
    kept = turns[-limit:] if limit and len(turns) > limit else list(turns)
    return "\n".join(f"{t.role}: {t.text}" for t in kept)
