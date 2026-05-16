# Conversational Context + the Answer↔Action Seam — Design ("the guest has a real multi-turn conversation, and when it turns into a reservation change it always goes to the supervisor")

| | |
|---|---|
| **Status** | Approved design (2026-05-16) |
| **Scope** | Two stacked behaviours, one coherent journey segment: (1) a sliding **50-message conversation window** (guest input + system grounded-answer output, per active stay) fed as **prompt context** into the existing `decompose`/`classify`/`grounding` LLM calls — *extraction-only*, the deterministic D30 risk rulebook and D5 slot-completeness unchanged; (2) the **D24 answer↔action seam** — a context-dependent follow-up ("till 2pm?") becomes classifiable as a `check_out` reservation mutation, force-flags through the *already-built* `is_reservation_mutation` path, lands in the spine's decision queue, and on approve / edit / silent-auto-proceed the spine's **single** executor applies it to `stay.check_out`. |
| **Source of truth** | Product decisions (D-series) — *what*; architecture decisions (AD-series) — *how it runs*; the dispatch-spine design (`docs/superpowers/specs/2026-05-16-dispatch-spine-design.md`) — the substrate this stacks on; this doc — *this slice*. |
| **Depends on** | **dispatch-spine merging** (`feat/dispatch-spine`): `Recommendation` base + `_RecDetail` per-action detail tables + `ck_rec_action`; the pure `shared/domain/recommendation.build`; the single `shared/engine/spine.apply_recommendation` executor (`_REC_DETAIL` / `_resolved_action` / `_execute_action` / `_assemble_context`); the merged `shared/events.writer` extended-emit idiom; the C4 `lifecycle.transition` orchestrator + the `ChildState` matrix (`triaged→answered→closed` closure-lite arc); the spine-widened `child_sub_request` (its additive `priority_tier`/`closure`/`revised_eta`/`predecessor_child_id` columns + widened `ck_child_state`); the supervisor decision-queue + its per-action editable form; migration `0005_dispatch_spine`. Authored **docs-only now (zero merge risk)** on `main`; executed after the spine lands. Migration is the **sixth** Alembic version (`down_revision='0005_dispatch_spine'`). The merged no-dispatch substrate is also a dependency (intake, `triage.classify`, `grounding.ground`, the `rdal`/`cdal`/`resdal` conversation read model, the `is_reservation_mutation` issue-code attribute + the "Resolution A" force-flag already in `triage.classify`). |

## 1. Why this slice

Slicing is by **journey segment** — every slice closes a real, demoable gap and stacks on the previously-proven substrate, authored docs-only while its predecessor is in flight (the exact auth→stay/binding→no-dispatch→staffing→spine cadence). The spine delivers *a request reaches a human and nothing is silently lost*. But two journey gaps remain that the spine deliberately deferred as stated seams:

- **The conversation is stateless.** `triage.classify(text, catalog)` and `grounding.ground(question, kb, facts)` see only the current message. A guest cannot have a *conversation* — every message is processed in isolation. "What time is checkout?" → "11am" → "can I get it till 2pm?" is unintelligible: the follow-up has no anchor.
- **The answer↔action seam is unbuilt (D24).** The spine wired the *generic* D30 FLAG trigger and `triage.classify` already force-flags any issue code with `is_reservation_mutation=true` ("Resolution A"). But there is **no executor that applies a reservation mutation** — the spine's `_execute_action` handles reassign/broadcast/relocate/extend_sla/approve/deny, not "change `stay.check_out`". A late-checkout request can be detected and flagged but never *fulfilled*.

These two are one journey: the seam *only works* with the window (the follow-up is only classifiable as a late-checkout mutation because the LLM sees the prior checkout turn). This slice closes that segment. It is the **smallest, lowest-surface slice in the project** — 0 endpoints, 0 new entities, 0 new UI surfaces — its weight is in conversational behaviour, not new surface; the deliberate opposite of the big-bang spine.

## 2. Scope

**In:**

- A pure `shared/domain/conversation.py`: pre-fetched transcript rows → a bounded **last-50** history string. No DB, no I/O, no clock (the `grounding.py` purity contract verbatim).
- Window source = **the exact read model `GET /guest/requests` already uses**: `rdal.list_requests_for_guest` → `cdal` children → `resdal` resolutions. Guest turn = `request.raw_text`; system turn = `resolution.answer_text`. Filtered to the **active stay** (`request.stay_id`), ordered by `created_at`, last 50. Survives relocation (same stay, new room — D20).
- Additive optional `history=""` param on `triage.classify` and `grounding.ground` (defaults preserve every existing test/behaviour); `shared/integrations/openai.py` injects `history` into the classify/ground prompt above the current message. **50 is a `core` settings constant** (not supervisor CONFIG — a turn-window is not operational structure a supervisor tunes; YAGNI).
- The **extraction-only invariant**: history changes only *what the LLM extracts*. The issue-code → deterministic rulebook → outcome path is the same pure function as today. D5/D30 untouched.
- The **D24 executor**: a new recommendation action `apply_reservation_mutation` carrying `{field:'check_out', requested_value}`, threaded through the spine's existing additive patterns — `_ACTIONS`/`ck_rec_action` widened, a `RecApplyReservationMutation` `_RecDetail`, `_REC_DETAIL`/`_resolved_action`/`_execute_action`/`_assemble_context` extended, the pure `recommendation.build` `triage_flag` branch extended. The executor resolves the `Stay` via the spine's existing `child→Request→Stay` chain, mutates `stay.check_out`, emits exactly one `reservation_mutated` append-only event, and drives the child to closure via the merged C4 closure-lite arc.
- One additive nullable column `child_sub_request.requested_checkout timestamptz` (see §4 — the auto-proceed-safety requirement) + an additive optional `requested_checkout` kwarg on `cdal.insert_child` + an additive optional field on `triage.TriagedChild`.
- One frontend delta: a datetime field variant for `apply_reservation_mutation` inside the spine's *already-existing* per-action decision form (sibling of `rec_relocate`/`rec_extend_sla`).
- A layered test bench (§6) extending the merged spine harness; an e2e seam sentinel.

**Out (by decision, not omission — stated seams):**

- **System-output fidelity** — acks / clarify-questions / split-echoes are computed at request time and **not persisted** by the reused read model. The window therefore contains guest text + grounded answers + state, **not** the system's own transient prompts. Clarify-resume coreference ("4" → "4 what?") stays weak until a later slice persists system outputs. Conscious boundary; fully serves the D24 seam.
- **D35 multi-intent fan-out** — its own later slice once the spine is merged & stable (re-opens WorkOrder-lineage / Glitch-\*-shape). This slice stays single-intent (1 message → 1 `Request` → 1 `ChildSubRequest`), inheriting the spine's 1:1.
- **`reservation_facts` / billing / rate / room-type model** — stays deferred (D32/D24). The only automatable mutation is `stay.check_out` (late checkout / extra night). **Upgrade / room change** reuses the merged `relocate_stay` seam (an upgrade is mechanically a relocation — no new mechanism). **Billing / comp** has no entity; it remains a manually-recorded value (the Glitch `recovery_cost` precedent), not automation (D19-spirit).
- **Structured dialogue state** — explicitly rejected (extraction-only chosen). No conversation state machine, no durable "B references A" link beyond the spine's already-inert `predecessor_child_id`. D30 "rules not vibes" preserved literally.
- **D38 modify** — still cancel-only; `predecessor_child_id` stays the spine's inert seam.
- **Out-of-band notification (D42)**, **voice/i18n (D11/D41)**, **analytics read side (D1/D28)** — inherited product boundaries; the answer↔action outcome streams into the same event log the deferred analytics reader will consume.

## 3. Dependency & sequencing

Hard dependency on **dispatch-spine merging**. Authored docs-only now (zero merge risk) on `main`, executed after the spine lands, stacking on its merged state — the established cadence. Migration is the **sixth** Alembic version (`down_revision='0005_dispatch_spine'`).

**Coupling, named honestly.** Unlike the context-window half (pure-domain + a thin intake edit, zero spine coupling), the D24 half **edits spine-owned files additively**: `shared/domain/recommendation.py` (`build` `triage_flag` branch + `_ACTIONS`), `shared/engine/spine.py` (`_REC_DETAIL`, `_resolved_action`, `_execute_action`, `_assemble_context`), `shared/events/writer.py`, `shared/models/recommendation.py` + `event.py` + `__init__.py`, and the spine-widened `child_sub_request.py`. Every edit is the *additive extension the spine's own code comments pre-authorize* ("New action later = new detail + one CHECK value (additive — the event-detail idiom)"). No spine behaviour is rewritten; no spine route/contract changes. This coupling is intrinsic — D24 *is* an answer↔action seam **through** the escalation spine; it was always going to live there. It can only execute post-spine-merge; as a docs-only spec it carries zero merge risk against the in-flight spine.

**No big-bang.** This is the project's smallest cut. The phased internal structure (window pure-domain → intake wiring → model/migration → recommendation/executor → frontend field → bench) builds incrementally and lands as one small additive PR.

## 4. Decision ledger

| Area | Locked decision |
|---|---|
| Slice cut | Conversation window + D24 answer↔action seam, single-intent, additive on the merged spine. D35 fan-out deferred to a later slice. |
| Context role | **Extraction-only (LLM-boxed).** History is prompt context for `decompose`/`classify`/`grounding`; the deterministic D30 rulebook + D5 slot-completeness are unchanged. No structured dialogue state, no durable references beyond the inert `predecessor_child_id`. |
| Transcript store | **No new store.** Projected from the existing `rdal`/`cdal`/`resdal` read model (`request.raw_text` + `resolution.answer_text`), per active stay, last 50 by `created_at`. Reuses the exact path `GET /guest/requests` already serves. |
| Window fidelity | **Reuse as-is, accept the boundary.** Transient system outputs (acks/clarify-Qs/split-echoes) are not persisted → not in the window. Stated seam; serves the D24 seam fully. |
| Window assembly | A **new pure `shared/domain/conversation.py`** function (no DB — the `grounding.py` precedent). The DB read belongs to the caller (`guest/services/intake.py`). |
| Window bound | **50 messages**, a `core` settings constant. Not supervisor CONFIG (YAGNI). |
| Mutation scope | **`stay.check_out` only** (late checkout / extra night). Upgrade reuses merged `relocate_stay`; billing/comp = manual field. **No new stateful table; `reservation_facts` stays deferred.** |
| Requested-value durability | The LLM-extracted target datetime is persisted at intake on **one additive nullable column `child_sub_request.requested_checkout`**, so the pure `recommendation.build` and the deterministic auto-proceed executor **never invoke the LLM** (the spine `_stub_llm` "LLM is boxed" / auto-proceed-safety invariant — D5/D30). Consistent with the spine's own additive child-column pattern. |
| Recommendation action | **New `apply_reservation_mutation`**, additive: `_ACTIONS` + `ck_rec_action` widened; a `RecApplyReservationMutation(_RecDetail)` detail (`field text+CHECK(check_out)`, `requested_value timestamptz`); `_REC_DETAIL` map + `_resolved_action` extended. Exactly the spine's `rec_relocate`/`rec_extend_sla` idiom. |
| Builder | The pure `recommendation.build` `triage_flag` branch: if context carries a reservation mutation (`requested_checkout` present) → `apply_reservation_mutation` with templated rationale (stub-rendered, deterministic); else the existing `approve`/`deny`. The action/params remain pure-Python deterministic — the LLM seam still only renders rationale text. |
| Executor | A new branch in the spine's `_execute_action`: resolve `Stay` via the existing `child→Request→Stay` chain, set `stay.check_out = requested_value`, emit one `reservation_mutated` via the writer, drive the child through the merged C4 closure-lite arc (`triaged→answered→closed`). `_resolved_action` reads `RecApplyReservationMutation` for the `approved`/`auto_proceeded` stored-rec path → **silence ≡ approve stays structural** (the spine's one-executor symmetry, now exercised through a mutation). |
| Child closure | **No new child states.** Reuse the merged closure-lite arc (the no-dispatch `triaged→answered→closed`, already in the spine `ChildState` `_LEGAL` matrix). The mutation outcome ("checkout now 2pm") is the child's "answer". |
| Events | Bespoke `emit_reservation_mutated(s, stay_id, field, old_value, new_value, actor)` (not `_emit_one` — carries payload beyond a single FK; follows the `emit_request_created` bespoke shape). `event.type` `ck_event_type` widened += `reservation_mutated`; `EventReservationMutated` detail. Append-only: no update/delete path. |
| API | **Zero new endpoints.** Intake reuses `POST /guest/requests`; the flag rides `GET /supervisor/decisions`; resolve rides `POST /supervisor/decisions/{id}/resolve` with one new payload **variant** (a `requested_value` datetime), validated through the same handler. No `/auth` change. No-`DELETE`→`405` invariant intact. |
| Frontend | One datetime field variant in the spine's existing per-action decision form. No new page/component/hook/route/nav. Window is invisible to every portal. |
| Layering | Identical to merged slices: `api → services → dal → shared/models`; pure mechanism in `shared/domain`; spine effecting in `shared/engine`; DAL add-only/no-flush/no-commit; service flushes; engine has its own engine-local reads (the spine idiom). No new exception class (merged `core/exceptions` only). No jsonb, no PG enums (`text + CHECK`), every column a real FK or scalar. |

## 5. Module ownership & layout

```
shared/domain/        conversation.py   (NEW, pure: rows → bounded last-50 string)
                      triage.py         (modify: classify(...,history="") +
                                          TriagedChild.requested_checkout opt field)
                      grounding.py      (modify: ground(...,history=""))
                      recommendation.py (modify: triage_flag branch →
                                          apply_reservation_mutation; _ACTIONS +=)
shared/engine/        spine.py          (modify, additive: _REC_DETAIL,
                                          _resolved_action, _execute_action,
                                          _assemble_context triage_flag branch)
shared/events/        writer.py         (modify: + emit_reservation_mutated bespoke)
shared/integrations/  openai.py         (modify: inject history; classify extracts
                                          requested_checkout for mutation children)
shared/models/        recommendation.py (modify: widen ck_rec_action +
                                          RecApplyReservationMutation _RecDetail)
                      event.py          (modify: widen ck_event_type +
                                          EventReservationMutated detail)
                      child_sub_request.py (modify: + requested_checkout col)
                      __init__.py + __all__ (register the 2 new detail classes
                                          in firm order, after the spine's)
core/                 config/settings   (modify: CONVERSATION_WINDOW = 50)
guest/dal/            children.py       (modify: insert_child(...,
                                          requested_checkout=None) opt kwarg)
guest/services/       intake.py         (modify: read transcript via rdal/cdal/
                                          resdal → conversation.window → pass
                                          history to classify + nodispatch
                                          grounding; persist requested_checkout)
migrations/versions/  0006_conversation_answer_action.py
                      (down_revision='0005_dispatch_spine')
tests/                conftest reuse + layered modules + e2e seam sentinel
frontend/             one datetime field variant in the spine decision form
```

No API routing change (sub-routers, gates, `__init__` registrations untouched — 0 new routes). Identical conventions to the merged structure.

## 6. Data model

`text + CheckConstraint` for every enum (no PG enums, no jsonb); `timestamptz` via `DateTime(timezone=True)`; additive `ALTER`s only, never data migrations (the `ck_event_type` precedent the spine itself uses). Registered so the **sixth** autogenerate sees them, stacked on `0005`.

### `child_sub_request` (modify — additive)
Add `requested_checkout timestamptz` **nullable**. Set at intake **only** for a child the LLM extracted a checkout-mutation target for (extraction step — LLM allowed under D5; "the AI always prepares"). Read by `spine._assemble_context` (`triage_flag` branch) to feed the pure builder, and copied into `RecApplyReservationMutation.requested_value`. Nullable, never backfilled — the additive-ALTER pattern; the spine's `priority_tier`/`closure`/`revised_eta`/`predecessor_child_id` precedent verbatim. **No change to `ck_child_state`** (closure reuses the spine-merged `triaged→answered→closed` arc).

### `rec_apply_reservation_mutation` `SPINE-detail` (new — `_RecDetail` subclass)
| col | type | notes |
|---|---|---|
| `recommendation_escalation_id` | uuid **pk fk→recommendation.escalation_id** | the `_RecDetail` abstract-base idiom verbatim |
| `field` | text + CHECK`(field='check_out')` | the only v1 mutable reservation field (D32-bounded); a future field = one CHECK value (additive) |
| `requested_value` | timestamptz **not null** | the LLM-extracted target checkout (from `child.requested_checkout`) |

Added to `_REC_DETAIL` in `spine.py`: `"apply_reservation_mutation": lambda eid, p: RecApplyReservationMutation(recommendation_escalation_id=eid, field=p["field"], requested_value=p["requested_value"])`.

### `event_reservation_mutated` `EVENT-detail` (new)
| col | type | notes |
|---|---|---|
| `event_id` | uuid **pk fk→event.id** | the event-detail idiom |
| `stay_id` | uuid **fk→stay** | the mutated stay |
| `field` | text + CHECK`(field='check_out')` | |
| `old_value` | timestamptz not null | pre-mutation `stay.check_out` (captured before the write) |
| `new_value` | timestamptz not null | applied value (== `requested_value`, or the supervisor-edited value) |

Emitted via a **bespoke** `emit_reservation_mutated` (the `emit_request_created` shape — `_emit_one` only carries a single FK; this carries payload).

### CHECK widenings (additive `ALTER`)
- `recommendation` `ck_rec_action` += `'apply_reservation_mutation'`.
- `event` `ck_event_type` += `'reservation_mutated'`.

### Migration `0006_conversation_answer_action`
`down_revision='0005_dispatch_spine'`. Creates `rec_apply_reservation_mutation` + `event_reservation_mutated`; `ALTER` `ck_rec_action` + `ck_event_type`; `ADD COLUMN child_sub_request.requested_checkout` (nullable). `upgrade→downgrade` round-trips clean; the `field` CHECK rejects anything ≠ `'check_out'`; both detail pk-fks reject an orphan; the widened CHECKs accept the new value and still reject garbage; existing rows survive untouched (additive — no data migration).

## 7. Mechanism

### 7.1 The conversation window — pure `shared/domain/conversation.py`
No DB, no clock. Input: already-fetched transcript rows (the caller's `rdal`/`cdal`/`resdal` reads, scoped to the active stay). Output: a bounded string of the **last 50** messages, chronological, role-labelled (`guest:` from `request.raw_text`, `system:` from `resolution.answer_text`), oldest dropped past 50 (the sliding bound), length-capped. Pure — exactly the `grounding.ground` contract ("the DB read belongs to the caller, never here").

`guest/services/intake.py` (the only non-spine, non-pure edit): before `triage.classify`, read the active stay's transcript via the **existing** DAL, build the window string via `conversation`, pass it as `history=` into `triage.classify` and into the `nodispatch` grounding path. When `classify` returns a `TriagedChild.requested_checkout`, persist it via `cdal.insert_child(..., requested_checkout=...)`. Per-stay scoping is inherent (`request.stay_id`); survives relocation (same stay).

### 7.2 Extraction-only — the D30 invariant
`shared/integrations/openai.py` `classify`/`ground` inject `history` above the current message so the LLM resolves coreference ("it", "that", "till 2pm"). The LLM's *extraction* improves; the issue-code → deterministic rulebook → outcome path (`triage.classify`'s "Resolution A" force-flag on `is_reservation_mutation`) is **byte-identical** with or without history. History can never raise/lower a risk decision — it only changes which structured child the LLM emits. The "AI prepares, rules decide" line (D5/D30) holds literally; this is asserted as a signature test (§11 test bench).

### 7.3 The answer↔action seam — emergent, not special-cased
There is **no seam-detection code**. The seam *emerges* from three already-aligned pieces:
1. the window lets the LLM classify the context-dependent follow-up ("till 2pm?") to the `late_checkout` issue code (which the supervisor configured `is_reservation_mutation=true`);
2. `triage.classify`'s **existing** "Resolution A" forces `outcome="flag"` for that code (built in no-dispatch, untouched here);
3. the spine's **existing** generic FLAG path opens an `Escalation` + `Recommendation` and routes it to the decision queue.

This slice adds only the **fulfilment**: `recommendation.build`'s `triage_flag` branch emits `apply_reservation_mutation` (params `{field:'check_out', requested_value: child.requested_checkout}`, surfaced through `_assemble_context`), and `spine._execute_action` gains the branch that resolves the `Stay` (the existing `child→Request→Stay` chain — imports already present in `spine.py`), captures `old_value`, sets `stay.check_out = requested_value` (or the supervisor-edited value via the existing `edited`/`overridden` path), emits one `reservation_mutated` event, and drives the child through the merged C4 closure-lite arc. The `approved`/`auto_proceeded` stored-rec path in `_resolved_action` reads `RecApplyReservationMutation` → **silence ≡ approve remains structural** (the spine's one-executor guarantee, now carrying a mutation; D9). The D21 bound, the supervisor-SLA timer, edit/override — all inherited unchanged.

## 8. API surface

**Zero new endpoints.** Inherited conventions hold (cookie session, per-handler role gate, domain errors, `extra="forbid"`, commit at the edge, no-`DELETE`→`405`).

- `POST /guest/requests` (merged) — behaviour enriched (intake feeds the window); no signature change.
- `GET /guest/requests` (merged) — unchanged; it is the transcript *source*; the guest also sees the mutation outcome on the existing status card.
- `GET /supervisor/decisions` (spine) — the force-flagged mutation appears as a normal decision item; no change.
- `POST /supervisor/decisions/{id}/resolve` (spine) — one new **payload variant** (a `requested_value` datetime for the `apply_reservation_mutation` action) validated through the same handler; not a new route. Auto-proceed runs the same `apply_recommendation` server-side (no API call) — symmetry preserved.

The route/contract snapshot **must NOT drift** — asserted as the positive proof of zero added surface (the deliberate inverse of the spine, which consciously regenerated it).

## 9. Journeys, flows, dataflow

### 9.1 Per-actor
- **Guest:** asks in plain text as today; the conversation now *coheres* across turns (the window is invisible plumbing — no UI change). A reservation follow-up ("can I get late checkout till 2pm?") is understood, acknowledged, and — because it mutates the reservation — the guest is told it's being confirmed; the outcome ("your checkout is now 2pm") appears on the existing status card; closure-lite closes it.
- **Supervisor:** the mutation lands in the **existing decision queue** as a normal item with an AI recommendation (`apply_reservation_mutation`, a templated rationale, the supervisor-SLA countdown). One tap approves; the editable form (one new datetime field) lets them trim 2pm→1pm; **silence past the supervisor-SLA auto-proceeds identically** (the spine's structural symmetry). The D21 backstop is inherited unchanged.
- **Duty manager:** inherited spine sub-actor — a mutation escalation that exhausts N cycles hard-escalates exactly as any other (non-time-boxed, never auto-proceeds).

### 9.2 The flow (fully walkable)
*"what time is checkout?"* → no-dispatch grounded answer "11am" (closure-lite; persisted to `resolution`) → *"can I get it till 2pm?"* → intake assembles the 2-turn window → `classify(history=…)` resolves the `late_checkout` mutation code → **"Resolution A" force-flag** (existing) → spine `Escalation` + `recommendation.build` ⇒ `apply_reservation_mutation{check_out, 2pm}` → decision queue → **(a)** supervisor approves → `_execute_action` sets `stay.check_out=2pm`, emits one `reservation_mutated`, child → closed; **(b)** supervisor silent → supervisor-SLA timer (`fire_at`-past + `tick`) → `auto_proceeded` → **identical end state as (a)**; **(c)** supervisor edits 2pm→1pm → `stay.check_out=1pm`. *The window + the seam are why this flow is intelligible at all.*

### 9.3 Dataflow

| Producer | Data / event | Consumer |
|---|---|---|
| `guest/services/intake` | active-stay transcript (existing `rdal`/`cdal`/`resdal`) → `conversation.window` → `history` string | `triage.classify`, `nodispatch` grounding |
| `triage.classify` (history-aware extraction; rulebook unchanged) | `TriagedChild{issue_code=late_checkout, outcome=flag (Resolution A), requested_checkout}` | `intake` → `child.requested_checkout`; the spine FLAG path |
| spine `open_escalation` → `_assemble_context` (triage_flag) | `{verdict, requested_checkout}` | pure `recommendation.build` |
| `recommendation.build` | `apply_reservation_mutation{field:check_out, requested_value}` + templated rationale | `Recommendation` + `RecApplyReservationMutation`; decision queue |
| supervisor resolve **— or supervisor-SLA silence** | `apply_recommendation` (one executor) | `_execute_action` mutation branch |
| `_execute_action` | `stay.check_out` mutated; one append-only `reservation_mutated`; child → closure-lite | guest status card; awareness/decision projections; deferred analytics |

**Invariants:** history feeds extraction, never the risk decision (D30 intact); the LLM is never in the auto-proceed path (value persisted at intake → deterministic downstream); silence ≡ approve stays structural (one executor); exactly one append-only event per mutation; zero new endpoints/entities/UI; every edit additive on the merged spine.

## 10. Frontend

Reuse the merged uniformity layer verbatim. The window is invisible (backend plumbing). The single delta: the spine's existing per-action decision form gains **one variant** — a datetime input bound to `requested_value` for the `apply_reservation_mutation` action — exactly how `rec_relocate` renders a room picker and `rec_extend_sla` a seconds field. No new page, component, hook, route, or nav. The guest sees the outcome via the spine's existing status-card/closure-lite rendering (no new component).

## 11. Test bench

**Guarantee:** "pass ⇒ no manual re-check" for every documented behaviour **and** the inherited guarded classes (route/contract drift, response-shape, role-gap, append-only, timer non-fire). Extends the merged spine `conftest` (unconditional savepoint-rollback + leak sentinel); timers driven by `fire_at`-past + synchronous `engine.tick` (engine loop disabled) — the spine harness verbatim.

- **Migration `0006`:** `down_revision=='0005_dispatch_spine'`; up/down round-trips; `field` CHECK rejects ≠`check_out`; both detail pk-fks reject orphans; `ck_rec_action`/`ck_event_type` accept the new value, still reject garbage; `requested_checkout` add is nullable; existing rows survive.
- **Pure window:** empty→empty; `<50` all chronological; `>50` exactly the last 50 (sliding); guest/system rows interleaved by `created_at`, correctly role-labelled; **per-stay isolation** (a second stay never leaks); **survives relocation**; asserts no DB/session touched (purity); output length-capped.
- **The D30 invariant (signature test):** `classify(...,history="")` ≡ today (additive-param back-compat); with history, "till 2pm" after a checkout answer resolves to `late_checkout`; for the *same extracted issue code* the outcome is **byte-identical with/without history**; a mutation code still force-flags, a non-mutation still doesn't; `ground` with history still **never free-forms** (D26).
- **`recommendation.build`:** a reservation-mutation `triage_flag` context → `apply_reservation_mutation{check_out, requested_value}` + deterministic templated rationale (stub seam); non-mutation flags still build `approve`/`deny` (no regression); action/params never LLM-derived.
- **Executor (`_execute_action` + `_resolved_action`):** approve → `stay.check_out=requested_value`, exactly one append-only `reservation_mutated` (correct `old_value`), child→closed, escalation resolved; edit 2pm→1pm → applied value = edited; deny/override → no stay change, no `reservation_mutated`; **silence/auto-proceed ≡ approve** asserted as post-state equality (the one-executor symmetry through a mutation — signature test); inherited D21 bound + already-resolved→`409` still hold for the new action.
- **Service (intake):** the assembled history reaches `classify` + `nodispatch` grounding (seam wired, not dead); `requested_checkout` persisted on the child; per-stay scoping end-to-end; no-active-stay path unchanged; **AD11 LLM-unavailable degrade** still conservative-clarifies with the new param (never a silent drop); exactly one append-only event per mutation.
- **E2E seam sentinel (one scripted test = the journey):** supervisor seeds presets/ladder + a `late_checkout` `is_reservation_mutation` code → "what time is checkout?" → grounded answer persisted → "can I get it till 2pm?" → window → classify → force-flag → escalation+recommendation → branch (a) approve, (b) silent-auto-proceed (`fire_at`-past + `tick`) **identical end state**, (c) edit → 1pm; asserts one append-only event, the seam needed **no special-case code**, zero residue on a failing run (savepoint isolation).
- **Structural guards (inherited free — asserted):** route/contract snapshot **does NOT drift** (zero-surface proof); auth-coverage meta-test green (no new routes); append-only no-update/no-delete holds for `reservation_mutated`; no-`DELETE`→`405` unchanged; `--cov-fail-under=90` maintained; the decision-form payload variant parses back through `extra="forbid"`.

**CI:** Postgres-required (physical CHECK/FK + `SKIP LOCKED` inheritance); full suite + coverage gate + savepoint isolation + leak sentinel; red blocks merge.

## 12. Verification bar ("done" means)

Migration `0006` applies on the spine's merged state and round-trips; a context-dependent follow-up is classifiable because the 50-turn window reaches the LLM, while the D30 risk decision is provably unchanged by history; a reservation-mutation follow-up force-flags through the existing path, the spine builds an `apply_reservation_mutation` recommendation deterministically (LLM never in the auto-proceed path — the value was persisted at intake), the supervisor approve path and the silent-auto-proceed path mutate `stay.check_out` **identically** via the single executor, edit/override/deny behave correctly, the child closes via the merged closure-lite arc, exactly one append-only `reservation_mutated` event is emitted per mutation; the route/contract snapshot is unchanged (zero added surface); the full layered + inherited + structural bench + the e2e seam sentinel is green under unconditional savepoint isolation with zero residue on failure.

## 13. Open / deferred (named, not silent)

- **System-output fidelity** — acks/clarify-Qs/split-echoes not persisted; clarify-resume coreference weak until a later slice persists them.
- **D35 multi-intent fan-out** — single-intent this slice; re-opens with WorkOrder-lineage / Glitch-\*-shape after the spine is merged & stable.
- **`reservation_facts` / billing / rate / room-type** — deferred (D32/D24); upgrade reuses `relocate_stay`, billing/comp stays a manual field.
- **D38 modify** — cancel-only; `predecessor_child_id` remains the spine's inert seam.
- **Analytics / bad-actor surfacing (D1/D28)** — the answer↔action outcome streams into the same event log the deferred reader will consume.
- **Window bound configurability** — 50 is a constant; supervisor-tunable only if a pilot demands it (YAGNI).
- **Out-of-band notification / voice / i18n (D42/D11/D41)** — inherited product boundaries.
