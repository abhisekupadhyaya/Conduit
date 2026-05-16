"""Casual-conversation terminal — orchestration only.

A child classified to the SMALLTALK issue code (a greeting / thanks /
chit-chat) is NOT a service request: it is not grounded against KB or
reservation, never queued for a human, and never "logged". It gets one
short, warm, bounded reply (no facts, no promises → D26-safe) and is
auto-closed (a greeting needs no guest confirmation, so no closure-lite).

Schema note (conscious, flagged): the reply is stored on
NoDispatchResolution with mode='grounded_answer' to reuse the existing
answered terminal + child_answered event without a migration (the
concurrent staffing slice owns the migration chain; a 0004 would
collide). A dedicated mode='casual_reply' is the proper later cleanup.
DAL is add-only; this service flushes; the API handler commits.
"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from conduit.guest.dal import resolutions as rdal
from conduit.shared.domain import lifecycle
from conduit.shared.integrations import openai as llm
from conduit.shared.integrations.openai import LLMUnavailable

_FALLBACK = "Happy to help — what can I get for you during your stay?"


async def resolve(s: AsyncSession, child, actor_id) -> dict:
    try:
        reply = await llm.smalltalk(child.text)
    except LLMUnavailable:
        reply = _FALLBACK
    await rdal.insert_resolution(s, child_id=child.id,
        mode="grounded_answer", answer_text=reply)
    await s.flush()
    await lifecycle.transition(s, child, "answered",
        actor_account_id=actor_id, resolution_child_id=child.id)
    await lifecycle.transition(s, child, "closed",
        actor_account_id=actor_id)
    return {"terminal": "answered", "answer": reply, "closure_prompt": False}
