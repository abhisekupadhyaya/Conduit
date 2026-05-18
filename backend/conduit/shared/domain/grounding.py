"""Grounding mechanism — cross-portal domain logic (not a portal slice).

Spec §7 (Call 2). Pure mechanism (no DB, no session): build the bounded
CONTEXT string from active KB rows + reservation/ambient fields, hand it to
the bulkheaded LLM (AD11), and return its typed result unchanged. The DB read
of active KB / ambient facts belongs to the caller, never here.
"""
from __future__ import annotations

from conduit.shared.integrations import openai as llm


async def ground(question: str, *, kb: list[dict], facts: dict,
                 history: str = "") -> dict:
    """Build the bounded CONTEXT string and hand it to the bulkheaded LLM.

    ``history`` is extraction-only context: it is forwarded *solely* to
    ``llm.ground`` and never participates in the deterministic CONTEXT-string
    construction. With ``history=""`` (default) the call is byte-identical to
    the prior two-argument call (back-compat).
    """
    lines = [f"- Reservation: room {facts['room_label']}, section "
             f"{facts['section_label']}, check_in {facts['check_in']}, "
             f"check_out {facts['check_out']}, status {facts['stay_status']}",
             "- Knowledge base:"]
    for e in kb:
        lines.append(f"[{e['id']}] {e['topic']}: {e['content']}")
    # Extraction-only: history forwarded ONLY to the LLM; default keeps the
    # legacy two-arg call byte-identical for back-compat.
    if history:
        return await llm.ground(question, "\n".join(lines), history)
    return await llm.ground(question, "\n".join(lines))
