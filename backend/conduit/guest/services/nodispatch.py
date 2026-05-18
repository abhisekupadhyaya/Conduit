"""No-dispatch resolution — orchestration only (Spec §7, Resolutions C/D/E/G).

The guest-side use-case for a no_dispatch child: read active KB (via the
supervisor DAL over shared models — a documented cheap cross-portal READ; the
guest portal does not own KB) + ambient facts, ground the question through the
bulkheaded LLM (mechanism in shared.domain.grounding), and either record a
grounded answer (→ answered + closure prompt) or defer to a human
(→ concierge_queue, terminal "logged"). DAL is add-only; this service flushes;
the API handler commits (Task 12).
"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from conduit.guest.dal import resolutions as rdal
from conduit.shared.domain import grounding, lifecycle
from conduit.shared.integrations.openai import LLMUnavailable
from conduit.supervisor.dal import kb as kbdal


async def resolve(s: AsyncSession, child, ambient: dict, actor_id,
                  history: str = "") -> dict:
    kb = [{"id": str(e.id), "topic": e.topic, "content": e.content}
          for e in await kbdal.list_entries(s, status="active")]
    facts = {"room_label": ambient["room_label"],
             "section_label": ambient["section_label"],
             "check_in": str(ambient["check_in"]),
             "check_out": str(ambient["check_out"]),
             "stay_status": ambient["stay_status"]}
    try:
        g = await grounding.ground(child.text, kb=kb, facts=facts,
                                   history=history)
    except LLMUnavailable:                             # AD11 degrade only
        g = {"grounded": False, "leaves_no_dispatch": False, "answer": "",
             "used_kb_ids": [], "used_fields": []}
    if g["grounded"] and not g["leaves_no_dispatch"]:
        await rdal.insert_resolution(s, child_id=child.id,
            mode="grounded_answer", answer_text=g["answer"])
        await s.flush()
        for e in kb:
            await rdal.insert_provenance_kb(s, child.id, e["id"],
                e["id"] in g["used_kb_ids"])
        for f in facts:
            await rdal.insert_provenance_field(s, child.id, f,
                f in g["used_fields"])
        await lifecycle.transition(s, child, "answered",
            actor_account_id=actor_id, resolution_child_id=child.id)
        return {"terminal": "answered", "answer": g["answer"],
                "closure_prompt": True}
    await rdal.insert_resolution(s, child_id=child.id, mode="human_deferral")
    await s.flush()
    await lifecycle.transition(s, child, "concierge_queue",
        actor_account_id=actor_id)
    return {"terminal": "logged"}
