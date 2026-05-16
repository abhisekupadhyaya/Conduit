"""Grounding mechanism — cross-portal domain logic (not a portal slice).

Spec §7 (Call 2). Pure mechanism (no DB, no session): build the bounded
CONTEXT string from active KB rows + reservation/ambient fields, hand it to
the bulkheaded LLM (AD11), and return its typed result unchanged. The DB read
of active KB / ambient facts belongs to the caller, never here.
"""
from __future__ import annotations

from conduit.shared.integrations import openai as llm


async def ground(question: str, *, kb: list[dict], facts: dict) -> dict:
    lines = [f"- Reservation: room {facts['room_label']}, section "
             f"{facts['section_label']}, check_in {facts['check_in']}, "
             f"check_out {facts['check_out']}, status {facts['stay_status']}",
             "- Knowledge base:"]
    for e in kb:
        lines.append(f"[{e['id']}] {e['topic']}: {e['content']}")
    return await llm.ground(question, "\n".join(lines))
