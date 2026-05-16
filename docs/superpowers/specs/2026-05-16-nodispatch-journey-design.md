# No-Dispatch Journey Slice — Design ("Ask → grounded answer, or honest deferral")

| | |
|---|---|
| **Status** | Approved design (2026-05-16) |
| **Scope** | The first SPINE journey: a checked-in guest asks in plain text → the system understands (decompose + mechanical triage), and for a no-dispatch intent answers grounded in reservation + supervisor KB, closes the loop (closure-lite), or honestly defers — including the supervisor config that *drives* those decisions |
| **Source of truth** | Product decisions (D-series) — *what*; architecture decisions (AD-series) — *how it runs*; data-model docs — *shape*; this doc — *this slice* |
| **Depends on** | The auth slice (merged) and the stay/binding slice (`feat/stay-binding`) merging — account model, cookie session, ambient `{stay,room,section}` resolution, the Event base + per-type-detail idiom, the test harness, the UI uniformity layer |

## 1. Why this slice

Slicing is by **journey segment**: every slice closes a real, demoable gap. Auth delivered *provisioned → login*. Stay/binding delivered *checked-in → session carries `{stay,room,section}`*. Every flow's precondition is then met but **nothing the guest asks for does anything yet** — there is no Request, no triage, no answer, no closure.

This slice closes the first runtime segment of the core promise — *"a guest asks, and the system resolves it with zero human coordination"* — taken at its **thinnest honest cut**: the **no-dispatch** terminal (Flow 04). It builds the shared SPINE substrate (Request → ChildSubRequest → mechanical triage → append-only Event) plus the one terminal that needs **no roster, no WorkOrder, no timers**: a grounded answer or an honest deferral. Dispatch/routing/escalation stack on this proven substrate later.

Crucially it also builds **the supervisor config that drives the automated decisions** — the `IssueCode` catalog (classification policy) and the `KBEntry` set (grounding facts). Without that, the slice would hardcode policy and only half-honour D34. With it, the slice is a genuine **cross-portal, multi-user journey**: *the supervisor sets the decision policy → the guest experiences decisions driven by it.*

## 2. Scope

**In:**

- `IssueCode` (CONFIG, **seed → supervisor-editable**: create / edit / disable; never delete) — the classification join point (D34).
- `KBEntry` (CONFIG, supervisor-curated: create / edit / disable; never delete) — the grounding source (D26).
- `Request` (SPINE container) and `ChildSubRequest` (SPINE — *the unit*, D35).
- Mechanical triage: LLM-assisted **decompose + classify**, then a **deterministic risk pass** that may only *raise* risk (D5/D30) and forces `FLAG` on a reservation-mutation code (D24).
- The **no-dispatch terminal**: grounded answer (reservation + active KB) → `ANSWERED`; closure-lite confirm → `CLOSED`/`REOPENED`; ungroundable / mutation-intent / LLM-unavailable → honest `human_deferral` → `CONCIERGE_QUEUE`.
- `NoDispatchResolution` + relational provenance (the D26 anti-hallucination audit).
- The generic append-only `event` taxonomy extended additively (write-only this slice).
- The third Alembic migration (`0003`, stacked on stay/binding's `0002`).
- Guest conversation surface (ask / status / closure-lite / **rehydration read**) and supervisor **Issue Codes** + **Knowledge Base** pages on the uniformity layer.
- A focused **design-system tightening** pass (its own first commit — see §13).
- A comprehensive backend test bench with savepoint-rollback isolation.

**Out (by decision, not omission — stated seams):**

- The **dispatch path** (routing D12/D18, WorkOrder, accept/progress/complete) — children with `outcome ∈ {auto,clarify,flag}` are recorded + evented (`child_parked`) and stop. The substrate is real; the dispatch terminal is a later slice.
- The **concierge-queue consumer / human deferral fulfilment** — the deferral *state + event* is born here; no servicer/queue UI picks it up this slice.
- **Timers / stall / the escalation spine** (D9/D10/D23) — no timers in no-dispatch.
- **CLARIFY budget** (D5) — an uncategorized/underspecified child is `outcome=clarify` then parked; the interactive clarify loop is a later slice.
- **Glitch** (D43/D44) — `is_problem_report` is computed and stored, inert this slice.
- **Cancel / modify** (D37/D38) — no `predecessor` lineage column.
- The generic event **read model** / awareness stream / analytics — the write seam is born here; the read side is deferred (the evolution seam, exactly as stay/binding deferred it).
- `reservation_facts` / SLA presets / escalation ladder / rosters / sections-rooms — other slices.
- Mass-events / dedup / idempotency / abuse (D27 trust boundary) — a re-send spawns a second request, consistent with the product boundary.
- Voice, i18n, out-of-band notification (D11/D41/D42) — inherited product boundaries, unchanged.

## 3. Dependency & sequencing

Hard dependency on **stay/binding merging** (ambient resolution, the Event base + per-type-detail idiom, the test harness, the UI primitives). This slice is authored **docs-only now (zero merge risk)** and **executed after stay/binding lands**, stacking on its merged state — the same cadence auth→stay/binding used. Its migration is the **third** Alembic version (`down_revision = 0002`). **Zero auth-owned / cross-slice code changes** — `/auth/me` already carries ambient; this slice reads its own binding via `guest/dal`. Only the route-contract snapshot regenerates. Lower merge risk than stay/binding (which had one cross-slice touch point).

## 4. Decision ledger

| Area | Locked decision |
|---|---|
| Slice cut | Thinnest honest SPINE substrate + the **no-dispatch** terminal only; dispatch/timers/clarify/glitch are stated seams. "Thin on spine machinery, complete on the no-dispatch journey including its config." |
| Config in scope | `IssueCode` + `KBEntry` are **supervisor CRUD** (seed → editable, **disable-not-delete**). Combined config+runtime in **one slice** (the full cross-portal journey). Sections/rooms/rosters/SLA/escalation explicitly out (other slices' decisions). |
| No jsonb | Every column a real FK or scalar; `text + CHECK` over PG enums; provenance is relational rows, not a blob. Identical to stay/binding. |
| Entities | `IssueCode`, `KBEntry`, `Request`, `ChildSubRequest`, `NoDispatchResolution` (own entity, entities.md Q7 resolved), `nd_provenance_kb`, `nd_provenance_field`; `event` CHECK extended + 7 per-type detail tables. |
| **Resolution A** | `is_reservation_mutation` is **system-owned**: absent from the create/patch request schema (sending it ⇒ `422` via `extra="forbid"`), set by seed, shown read-only in `IssueCodeOut`. A **deterministic triage pass** forces `outcome=FLAG` on a mutation-flagged code regardless of the LLM (D5/D30 — the LLM may only *raise* risk). Keeps D24/D30 intact while honouring D34 for mode/routing. |
| **Resolution B** | Principle reframed: thinnest on **deferred spine machinery**, complete on the no-dispatch journey + its config. Reviewability preserved via **layered commits** (the stay/binding worktree commit shape). |
| **Resolution C** | `POST /guest/requests` returns the answer/deferral **synchronously** (LLM bulkhead bounds the wait). D5 instant-ack satisfied **client-side** (TanStack mutation pending state shows "Looking into that…"), no polling machinery, no new endpoint. A deliberate, no-dispatch-scoped divergence from the literal D5 sequence. |
| **Resolution D** | closure-lite "no" → `ANSWERED → REOPENED` (emits `child_reopened`, D8's "a no reopens" honoured literally) → `CONCIERGE_QUEUE` (no re-ground loop, D25). Recorded as the closure-lite refinement D8 itself anticipates. |
| **Resolution E** | The guest conversation resolves ambient via its **own** `guest/dal/bindings.py` (a near-copy of `public/dal/bindings.py` over the same shared models) — consistent with stay/binding's locked self-containment principle ("the shared contract is the model, not the DAL"). No `public/`/auth dependency, no portal-cross-import. |
| **Resolution F** | `ensure_issue_codes()` is **insert-missing-by-`code` only, never update**. Supervisor edits/disables are authoritative and survive every reboot; future-release default codes are added missing-only. No auto "reset to default" (D29-spirit; accepted limitation, stated). |
| **Resolution G** | One-call grounding softens D26 to **model-asserted** provenance; mitigated by persisting the **full supplied context set** deterministically (`nd_provenance_*`), with the model's claimed subset advisory (`claimed_used`). Accepted tension, documented (LanceLive D28 idiom). |
| Lifecycle/event seam | The child state machine is **shared mechanism**: `shared/domain/lifecycle.transition(child, to)` is the single guarded transition that appends the matching event in the same txn (via `shared/events`). Portal services call it; portal DALs still own portal-specific entities. This keeps D6 ("interruptible from every state, every portal") consistent — the stay/binding portal-owned-events precedent was a single-portal case that did not expose this. |
| LLM | gpt-5.4-mini (pinned snapshot `gpt-5.4-mini-2026-03-17`, config-driven), OpenAI **Responses API** `responses.parse` + Pydantic `text_format`; reached only through the bulkheaded `shared/integrations` boundary (AD11); timeout + `tenacity` + circuit breaker → `LLMUnavailable` (503) → callers degrade, never block. Faked deterministically in CI. |
| Live policy | Catalog + KB are **read from DB on every request** (same posture as ambient re-resolution — never trust cached policy). A supervisor edit takes effect on the next request; no redeploy/re-login. Disabled codes are not offered to the classifier; disabled KB is not in grounding context. |
| Deletes | **No `DELETE` anywhere** (`405`, asserted invariant — mirrors auth + stay/binding). Reasons: cross-slice invariant; referential/audit integrity (`IssueCode`/`KBEntry` are referenced by children + provenance + the future read model); D29 lean. Supervisor "remove" = `status=disabled` (reversible, audit-safe). |
| Layering | `api → services → dal → shared/models`; fully async; DAL add-only/no-flush; services guard + raise domain errors + `flush`; the API handler `commit`s at the edge; reads never commit; ORM up, schema mapping at the API layer only. Identical to merged auth + stay/binding. |
| Errors | Domain errors via merged `core/exceptions` (`ConduitError`=400, `NotFoundError`=404, `AuthError`=401, `ForbiddenError`=403, `ConflictError`=409, `ValidationError`=422). `LLMUnavailable`=503 exists as a safety net but **never reaches the guest** — it is caught and degraded to deferral. No new exception class needed. |
| Portal ownership | Three self-contained portals; `public/` the pre-portal front door. Guest owns conversation/request/child/resolution reads+writes via `guest/dal`; supervisor owns `issue_code`/`kb` via `supervisor/dal`. The spine lifecycle/event seam is the one deliberate shared exception (above). |

## 5. Module ownership & layout

```
shared/models/        request.py child_sub_request.py issue_code.py kb_entry.py
                       no_dispatch_resolution.py provenance.py
                       event.py (modify: extend CHECK + add 7 detail classes)
                       __init__.py + __all__ (firm order: event✓ → request → child_sub_request)
shared/domain/        triage.py    (implement: decompose+classify, then the deterministic risk pass)
                       grounding.py (new: build bounded context prompt, call llm.ground; pure, no DB)
                       lifecycle.py (implement: guarded child transitions for the no-dispatch subset)
shared/events/        (implement: the append-only event+detail writer used by lifecycle.transition)
shared/integrations/  openai.py    (implement: AsyncOpenAI, Responses parse, bulkhead → LLMUnavailable)
core/                 (no change)
supervisor/dal/       issue_codes.py kb.py
supervisor/services/  issue_codes.py kb.py
supervisor/api/       issue_codes.py kb.py  (registered in supervisor/api/__init__.py)
supervisor/schemas/   issue_code.py kb.py   (extra="forbid"; request schema omits is_reservation_mutation)
guest/dal/            bindings.py requests.py children.py resolutions.py events.py
guest/services/       intake.py (implement submit_request + confirm) nodispatch.py
guest/api/            conversation.py (fill the stubs + add the rehydration GET)
guest/schemas/        conversation.py (RequestOut/ChildOut, extra="forbid")
conduit/seed          (extend: ensure_issue_codes — insert-missing-by-code only, idempotent)
```

API routing matches the merged structure: sub-routers carry a short prefix, composed by `<portal>/api/__init__.py`, `main.py` adds `/api`. Supervisor gating is **per-handler** `actor = Depends(_sup)`, `_sup = require_roles("supervisor","duty_manager")` (the `supervisor/api/accounts.py` shape). Guest gating `require_roles("guest")`.

## 6. Data model

`uuid` pk, `timestamptz`, `text + CHECK`, **no jsonb**, physical invariants via constraints. Registered so the **third** Alembic autogenerate sees them, stacked on `0002`.

### `issue_code` `CONFIG`
| col | type | notes |
|---|---|---|
| `id` | uuid pk | |
| `code` | text | **unique on `lower(code)`** (case-insensitive); global v1, multi-property denormalize later (AD9) |
| `label` | text not null | |
| `department` | text not null | open vocab |
| `fulfilment_mode` | text + CHECK`(dispatch\|no_dispatch)` not null | |
| `routing_model` | text + CHECK`(section_pooled\|skill_matched\|none)` not null | seed-set; **unread this slice** (forward scalar, the stay/binding `check_in/out` precedent — avoids a later migration; not a dangling FK) |
| `intent_kind` | text + CHECK`(service\|problem_report)` not null default `service` | D43 |
| `is_reservation_mutation` | bool not null default false | **system-owned** (resolution A) |
| `status` | text + CHECK`(active\|disabled)` default `active` | disable-not-delete |
| `created_at` / `updated_at` | timestamptz | |

### `kb_entry` `CONFIG`
`id` uuid pk · `topic` text not null · `content` text not null · `status` text+CHECK`(active\|disabled)` default `active` · `created_at`/`updated_at`. No topic-uniqueness.

### `request` `SPINE`
`id` uuid pk · `guest_account_id` fk→account · `stay_id` fk→stay · `raw_text` text · `channel` text+CHECK`(text)` default `text` (D11 seam) · `created_at`. `stay_id` is the binding snapshot at intake; "in-flight child on relocation" stays the deferred seam stay/binding flagged.

### `child_sub_request` `SPINE` — *the unit* (D35)
`id` uuid pk · `request_id` fk→request · `text` · `issue_code_id` fk→issue_code **nullable** (null ⇒ uncategorized) · `uncategorized` bool default false · `outcome` text+CHECK`(auto\|clarify\|flag\|no_dispatch)` · `fulfilment_mode` text+CHECK`(dispatch\|no_dispatch)` nullable · `is_problem_report` bool default false (D43, inert this slice) · `state` text+CHECK`(intake\|triaged\|answered\|concierge_queue\|closed\|reopened)` — **slice-scoped subset, extended additively** (the `event.type` CHECK idiom); a **parked** child (`outcome ∈ {auto,clarify,flag}`) terminates at `triaged` this slice (the dispatch/clarify states arrive with their slices) · `created_at`/`updated_at`. No `predecessor_id` (D37/D38 elsewhere).

### `no_dispatch_resolution` `SPINE` — own entity (entities.md Q7)
**`child_id` uuid pk fk→child_sub_request** (the 1:1 physical invariant) · `mode` text+CHECK`(grounded_answer\|human_deferral)` · `answer_text` text nullable (null on deferral) · `helpful` text+CHECK`(yes\|no)` nullable (closure-lite, D8-lite) · `created_at`.

### Provenance (the D26 mitigation, relational)
- `nd_provenance_kb` — pk`(resolution_child_id, kb_entry_id)`, both FKs, `claimed_used` bool default false.
- `nd_provenance_field` — pk`(resolution_child_id, field_name)`, `field_name` text+CHECK`(room_label\|section_label\|check_in\|check_out\|stay_status)`, `claimed_used` bool default false.

We persist the **full supplied set** deterministically; `claimed_used` flags the model's advisory subset.

### Event taxonomy
Extend the merged `event.type` CHECK additively to add `request_created, child_triaged, child_answered, child_deferred, child_parked, child_closed, child_reopened`. One thin per-type detail table each (`event_id` pk fk→event + typed FKs; `event_child_answered` also `resolution_child_id` fk). Append-only — no app update/delete path, asserted. *Honest note (same one stay/binding made):* the `child_*` detail tables are thin (often just `child_id`); kept so "every transition emits an event" uniformity holds, which is what makes the future awareness/analytics read model a clean read model. A later pass may collapse them; not now.

### Migration `0003_nodispatch`
`down_revision='0002_stay_binding'`; creates the tables + `ALTER` the event CHECK; `upgrade→downgrade` round-trips clean; every CHECK/FK rejects; `no_dispatch_resolution.child_id`-as-pk physically rejects a 2nd resolution per child; `lower(code)` unique index physically rejects a dup code.

## 7. The pipeline (mechanism)

`shared/domain/triage.py`:
- `decompose + classify(text, live_catalog) -> [TriagedChild]` via **LLM call 1** (Responses `parse`, structured) — one need = one child (D35); classify to exactly one active code or null (`uncategorized`); never invent a code.
- **Deterministic risk pass** (resolution A, D5/D30): post-LLM, code-side logic *forces* `outcome=FLAG` when the matched code is `is_reservation_mutation` (or a deterministic rule fires). The LLM may raise to flag, never lower. D24's always-flag is guaranteed for anything classified to a mutation code; free-text evasion is the known clarify-budget seam, stated, not an absolute claim.

`shared/domain/grounding.py`:
- `ground(question, context) -> GroundResult` via **LLM call 2** (resolution G): the prompt carries the **bounded context** = all *active* `KBEntry` + the guest's reservation/ambient facts (codes over names — the `openai.py` PII note). Output `{grounded, leaves_no_dispatch, answer, used_kb_ids, used_fields}`. `grounded=false` or `leaves_no_dispatch=true` ⇒ deferral.

`shared/integrations/openai.py`: `AsyncOpenAI(timeout=…)`, `responses.parse(model=settings.llm_model, input=[…], text_format=Schema, reasoning={"effort":"low"})` → `.output_parsed`; `tenacity` ≤2 attempts; circuit breaker opens after N failures (subsequent requests fast-degrade); exhaustion ⇒ `LLMUnavailable`. Static system preamble + KB **first** for the cached-input price tier. Model id/timeout config-driven; snapshot pinned for reproducibility.

### The prompts

**Call 1 — system (static; classify, not answer):** decompose into independent children; classify each to exactly one code from the injected `CATALOG` (active only) or null; `fulfilment_mode` from the matched code; `is_problem_report` only on objective broken/not-working framing (not tone); risk triggers (money/safety/moves/reservation change) ⇒ `flag`; never drop a need; unsure ⇒ `clarify` or `flag`, never omit. **User:** `{raw_guest_text}`.

**Call 2 — system (static; anti-hallucination):** answer ONLY from `CONTEXT`; insufficient ⇒ `grounded=false`, no answer (an honest "I'll have someone confirm" beats a wrong answer); answering requires a reservation/billing/room change ⇒ `leaves_no_dispatch=true`, `grounded=false`; on grounded, 1–3 plain sentences + the kb_ids/fields used. **User:** `QUESTION: {child_text}` + `CONTEXT` (reservation facts; active KB as `[id] topic: content`).

### The flow

```
POST /guest/requests {text}
  └ _guest → Actor; guest/dal/bindings.get_active_binding_for_guest
      └ no active stay ⇒ 409
  └ insert Request + flush; event request_created
  └ triage.classify (Call 1)               ── LLMUnavailable ⇒ 1 uncategorized child → human_deferral
  └ for each child: insert child + flush; deterministic risk pass;
      lifecycle.transition→TRIAGED; event child_triaged
      ├ no_dispatch ⇒ nodispatch.resolve
      │     gather active KB + reservation facts → grounding.ground (Call 2)
      │       ├ grounded & !leaves_no_dispatch ⇒ NoDispatchResolution{grounded_answer}+provenance;
      │       │     lifecycle.transition→ANSWERED; event child_answered
      │       └ else ⇒ NoDispatchResolution{human_deferral};
      │             lifecycle.transition→CONCIERGE_QUEUE; event child_deferred
      └ auto|clarify|flag ⇒ event child_parked; child stays TRIAGED
            (no further transition this slice — the stated seam)
  └ response: split-echo if >1 (D36) + per-child terminal + closure-lite prompt
  └ API handler: await s.commit()   (one request transaction throughout)

POST /guest/children/{id}/confirm {helpful}
  └ ownership guard (request.guest_account_id == actor.id else 404); state ANSWERED else 409
  ├ yes ⇒ lifecycle.transition→CLOSED; event child_closed
  └ no  ⇒ transition→REOPENED (event child_reopened) → CONCIERGE_QUEUE (event child_deferred)
```

## 8. API surface

Inherited conventions: cookie session; per-handler role gate (server-side regardless of client); domain errors `404/409/422`; response schemas `extra="forbid"`, internal fields never serialized; mutating handler `commit`s at the edge, reads never; **no `DELETE` → `405`, asserted**; `LLMUnavailable` never surfaces to the guest.

**Guest** (`/api/guest/*`, `require_roles("guest")`)
- `POST /requests` `{text}` → `200 RequestOut{request_id, children:[ChildOut]}`; no active stay → `409`. Synchronous (resolution C).
- `POST /children/{child_id}/confirm` `{helpful}` → `200 ChildOut`; not owner → `404`; not `ANSWERED` → `409`.
- `GET /requests` → `200 RequestOut[]` — the guest's own requests+children+answers (conversation rehydration; guest-owned read).
- `ChildOut{child_id, text, issue_code?, terminal:"answered"|"logged", answer?, closure_prompt?}` — the four internal terminals collapse to `answered` vs `logged` (Gap-2 honest unification: parked / concierge-deferral / LLM-degrade all render "Logged — a team member will follow up.").

**Supervisor — Issue Codes** (`/api/supervisor/issue-codes`, `_sup`)
- `GET ?status=` → `200 IssueCodeOut[]`.
- `POST` `{code,label,department,fulfilment_mode,routing_model,intent_kind}` → `201`. **No `is_reservation_mutation`** (resolution A). Dup `code` → `409`; bad enum → `422`.
- `PATCH /{id}` `{label?,department?,fulfilment_mode?,routing_model?,intent_kind?,status?}` → `200`; missing → `404`; dup → `409`; bad enum → `422`.

**Supervisor — Knowledge Base** (`/api/supervisor/kb`, `_sup`)
- `GET ?status=` → `200 KBEntryOut[]`.
- `POST` `{topic,content}` → `201`; empty content → `422`.
- `PATCH /{id}` `{topic?,content?,status?}` → `200`; missing → `404`.

**No API:** `event` + detail (write-only; read model deferred); `Request`/`Child`/`NoDispatchResolution` have no supervisor route (no decision queue/explorer this slice); `Property` (seeded by stay/binding). **No `/auth/me` / auth-owned change.**

Shapes: `IssueCodeOut{id,code,label,department,fulfilment_mode,routing_model,intent_kind,is_reservation_mutation,status,created_at}` (`is_reservation_mutation` display-only), `KBEntryOut{id,topic,content,status,created_at}`, `RequestOut`/`ChildOut` per above.

## 9. Journeys, flows, dataflow (the slice in the LanceLive idiom)

### 9.1 Per-actor journeys

- **Guest:** logged in + checked-in (ambient resolves) → asks in plain text → instant ack (client-side, resolution C) → split echo if >1 (D36) → per child: a **grounded answer + "Did this help?"** (closure-lite, D8-lite; yes ⇒ closed, no ⇒ honest deferral) **or** the honest **"Logged — a team member will follow up."** line (ungroundable D25 / mutation D24 / uncategorized D34 / LLM-down AD11 / dispatch parked D35). *Accepted honesty cost (LanceLive D42 idiom):* this slice builds **no human consumer** for parked/deferred children — "we'll follow up" is product intent, not a guarantee this slice fulfils; the closing seam is the dispatch + concierge-consumer slices. Stated, not papered over.
- **Supervisor:** views the **Issue Codes** catalog (seeded) → creates / edits / disables codes (`label`, `fulfilment_mode`, `routing_model`, `intent_kind`; `is_reservation_mutation` read-only, resolution A) → curates the **Knowledge Base** → both take effect **on the next request, live** (no redeploy). No decision queue / awareness stream (deferred). `duty_manager` shares the supervisor gate, no distinct journey.
- **Servicer:** no journey by design (no-dispatch).

### 9.2 Flows

- **Flow 0 (the cross-portal spine):** supervisor adds/edits a code or KB entry → the *next* guest question is classified/grounded by the new policy live → grounded answer or honest deferral.
- **A · grounded happy path:** ask → classify `no_dispatch` → ground (KB hit) → answer + closure-lite "yes" → `CLOSED`. Events: `request_created · child_triaged · child_answered · child_closed`.
- **B · ungroundable deferral:** ground `grounded=false` → `human_deferral` → `CONCIERGE_QUEUE`. Honest line. Events: `… child_deferred`. (Seam: no consumer.)
- **C · mutation intent (D24 answer↔action seam):** deterministic pass forces `FLAG` → `child_parked`. Honest line.
- **D · mixed multi-intent (D35):** one no_dispatch child answered now; one dispatch child parked. Split echo lists both; independent fate.
- **E · LLM down (AD11):** classify `LLMUnavailable` → conservative single `uncategorized` child → `human_deferral`. Never blocks, never drops; request + events still persisted.

### 9.3 Dataflow

| Producer | Data | Consumer |
|---|---|---|
| Supervisor · Issue Codes editor | `IssueCode` | classify Call 1 (read live every request) |
| Supervisor · KB editor | `KBEntry` (active) | grounding Call 2 (read live every request) |
| System · seed | default `IssueCode` set | classify Call 1 |
| Guest conversation | raw text + ambient (`guest/dal/bindings`) | `intake.submit_request` |
| `llm.classify` (Call 1) | `[TriagedChild]` (proposed) | the deterministic risk pass (disposes — may only raise) |
| `llm.ground` (Call 2) | `GroundResult` | `NoDispatchResolution` + provenance |
| `nodispatch.resolve` | `NoDispatchResolution{mode,answer,helpful}` | guest conversation (answer / closure-lite) |
| `lifecycle.transition` | `Event` + typed detail | **write-only this slice — no read model (seam)** |
| Guest confirm | `helpful` yes/no | closure (`closed` / `reopened→concierge_queue`) |
| parked / deferred children | children + events | **no consumer this slice** (stated seams) |

**Invariants visible in the flow:** the child is the unit, never the raw message (D35); nothing silently lost — every child is persisted **with an event even when its terminal is an unbuilt seam**; the one anti-hallucination boundary holds (grounded-only; ungroundable → honest deferral, D25/D26); events append-only/write-only — the read model is the evolution seam born here.

## 10. Frontend

Reuse the auth + stay/binding uniformity layer and conventions: TanStack Query (array keys, centralized invalidation, `api` client with `credentials:"include"` + 401→logout), `data-table-shell`/`page-header`/`empty-state`/`error-state`/`confirm`/`status-badge`, supervisor desktop-first / guest mobile-first. **shadcn add-then-edit always; never re-`add` an edited component; never hand-author.**

- **Install (only new shadcn this slice):** `scroll-area` (the guest transcript). The disable/enable toggle reuses the existing `Confirm` + dropdown-action pattern (no `switch`).
- **Compose new** (`components/common/`, edited tight): guest `chat-scroll`, `message`, `request-receipt`, `child-status-card`, `composer`, `closure-lite`; `issue-code-form-dialog`, `kb-entry-form-dialog` (cloned from `account-form-dialog`'s shape).
- **Hooks:** `shell/guest/hooks/use-conversation.ts` (`useConversation()` rehydration query `['conversation']`; `useSubmitRequest()` mutation — pending state *is* the instant-ack, resolution C; `useConfirmChild()`); `shell/supervisor/hooks/use-issue-codes.ts` and `use-kb.ts` (`['issue-codes']` / `['kb']`, create/update mutations invalidating by key prefix). Guest ambient stays on `useAuth()` context, never the query cache (the stay/binding rule).
- **Pages:**
  - **Guest `/guest`** — the whole portal is one screen (sitemap 1.2): centered single column (max-w ~640, edge-to-edge mobile); minimal header showing the **ambient room label** (the guest is *known*, never asked — D3a as a trust beat); `scroll-area` transcript (guest bubbles right, one concierge mark per system group); on send: optimistic guest bubble + a single restrained shimmer (no chatbot theatrics) replaced by the receipt (if >1) + per-child status cards; **answered** card = readable answer + ghost "Yes"/"No" closure-lite; **logged** card = calm muted line, never an alarm colour; sticky composer (auto-grow 1→5 lines, Enter=send/Shift+Enter=newline, ≥16px to kill iOS zoom, 44px targets, safe-area).
  - **Supervisor `/supervisor/setup/issue-codes`** — `sections.tsx` skeleton: `PageHeader` + `data-table-shell`; columns `code`(mono,tabular) · label · department · mode · intent · **mutation** (lock glyph + tooltip "System-owned — governs the always-flag policy, D24" — the lock is *taught*, not mysterious) · status (• dot); row `⋯` Edit / Disable·Enable→`Confirm`; reflows to cards `<md`; form dialog with enum `Select`s and `is_reservation_mutation` as a disabled, explained field.
  - **Supervisor `/supervisor/knowledge-base`** — `PageHeader` + `data-table-shell`: topic · content (truncate, row-expand via `collapsible`) · status dot; `⋯` Edit / Disable·Enable; form dialog (topic input + content `textarea`) with helper *"Answers are grounded only in active entries (D26)"* — the supervisor→guest causal link surfaced in-UI.
  - **Nav:** add "Issue Codes" under Setup and "Knowledge Base" as its own Setup entry in `nav-config.ts`; tighten the `supervisorNav` grouping while there.

## 11. Test bench

**Guarantee, stated honestly first:** "pass ⇒ no manual re-check" holds for every documented behaviour **and** the guarded classes below; it is **not** a guarantee against an unspecified requirement, and — the LLM is faked — **not** a guarantee about real model output. Inside that scope, green = comfort.

**Isolation — savepoint-rollback (the rollback-on-failure protection).** `tests/spine/conftest.py`: one connection + one **outer transaction** per test; `db` bound to it; the `db_session` override hands the *same* session to the app, so the app's edge `commit` lands in a `begin_nested()` SAVEPOINT (restarted via the `after_transaction_end` listener — the canonical pattern). Teardown **rolls back the outer transaction unconditionally — pass, fail, or exception**: nothing the test or the app inside it wrote ever persists. The merged FK-ordered delete + a **leak sentinel** (binding/spine tables at baseline between tests) are kept as a *fallback that must never fire* — if it does, something committed outside the test connection, and it fails loudly. Tests stay mechanism-agnostic (stay/binding pre-authorized this upgrade).

**LLM seam.** A programmable `FakeLLM` monkeypatches the `shared/integrations` boundary (zero network in CI): script N decomposed children/codes/outcomes, `grounded` true/false, `leaves_no_dispatch`, **raise `LLMUnavailable`**, trip the breaker — so every degrade path is tested deterministically.

**Layered:** *Migration* — `0003.down_revision==0002`, up/down round-trip, every CHECK/FK rejects, `child_id`-pk physically rejects a 2nd resolution, `lower(code)` rejects a dup (raw insert). *DAL* — add-only/no-flush, case-insensitive `get_by_code`, FK integrity, `get_active_binding_for_guest`, event-detail primitives. *Services/domain* — every guard branch; the **deterministic risk pass** (mutation code ⇒ `FLAG` even when FakeLLM says `no_dispatch` — the D24/D30 guard); conservative degrade. *API* — full stack via `httpx.AsyncClient(ASGITransport)`, real cookie chains, every endpoint happy + every error status.

**Structural guards (the whole-classes-of-change net).** Inherited free: the **auth-coverage meta-test** auto-sweeps the new supervisor + guest routes; the **contract snapshot** regenerated within this slice (route-surface drift ⇒ red); `secret_hash`/JWT guards exercise the new responses. Added: **(1)** response-shape parse-back through `extra="forbid"` (leaked/renamed field ⇒ red; guest `ChildOut` asserted to leak no internals); **(2)** the **resolution-A guard** — `is_reservation_mutation` present in `IssueCodeOut` but the request schema rejects it (send ⇒ `422`); **(3)** role×endpoint matrix; **(4)** append-only guard (one event + detail per transition; no event update/delete path); **(5)** idempotent-seed guard (twice ⇒ no dups; a supervisor-disabled/edited code survives a re-seed — resolution F); **(6)** live-policy guard (disable ⇒ next request reflects it — catches caching); **(7)** the existing `--cov-fail-under=90` (unchanged — raising it would move the bar for merged code).

**E2E journey sentinel:** supervisor creates+edits a code & KB entry → guest asks → grounded answer + events → closure-lite "yes" → `CLOSED` → ungroundable → honest deferral + `CONCIERGE_QUEUE` → supervisor disables the KB entry → same question now defers (live-policy) → mixed multi-intent (answered + parked, independent) → `LLMUnavailable` → conservative degrade, never 5xx, request+event persisted. Breaks loudly on any pipeline regression.

**CI:** Postgres required; full suite incl. coverage gate + savepoint isolation + leak sentinel; red blocks merge.

## 12. Verification bar ("done" means)

Migration `0003` applies on stay/binding's merged state and round-trips; the supervisor can seed-then-edit-then-disable codes & KB; a guest question grounded against supervisor-curated KB returns a grounded answer and closes via closure-lite; ungroundable / mutation / uncategorized / LLM-down all reach the honest "logged" deferral **with an event** and never block or drop; mixed multi-intent answers the no-dispatch child and parks the dispatch child independently; a supervisor edit/disable takes effect on the very next request (live policy); `is_reservation_mutation` is unsettable via the API and forces `FLAG` deterministically; every transition left exactly one append-only `event` + detail row; conversation rehydrates on reload; the full extended bench (layered + inherited + added structural guards + the e2e sentinel) is green under savepoint isolation; zero residue on a failing run.

## 13. Open / deferred (named, not silent)

- **Design-system tightening** — shipped as the slice's **isolated first commit** (`style(ui): tighten tokens + primitives`): `--radius 0.625→0.375`, rescaled radius ladder (cap `xl+` at `r*1.6`), hairline borders + `--border-strong`, `h-9` controls, type hierarchy by weight, status as a 6px dot, a **reserved-but-unused** `--accent-action` token, re-verify auth/stay/binding pages. A conscious override of stay/binding's "separate-PR" boundary (user-authorized); isolated to keep the diff reviewable.
- **Dispatch path / WorkOrder / routing / timers / escalation spine** — the immediate next slices; the substrate is built for them to stack on.
- **Concierge-queue consumer / human-deferral fulfilment** — the deferral state+event is born here; the consumer is a later slice.
- **CLARIFY budget** (D5), **Glitch** (D43/D44, `is_problem_report` inert), **cancel/modify** (D37/D38) — stated seams.
- **Generic event read model / awareness / analytics** — the evolution seam born here; read side deferred (as stay/binding deferred it).
- **`reservation_facts`** — returns in the D24 / late-checkout slice that consumes it.
- **Real-model evaluation** — outside the test-bench honesty claim; an offline eval harness is a separate concern.
- **No auto "reset to default"** for a supervisor-edited/disabled seeded code (resolution F) — accepted v1 limitation.
- **Multi-property** `property_id` denormalization (AD9) — additive when query patterns demand it.
- **Test-isolation** is now savepoint-rollback for this slice; revisiting the global harness to the same mechanism is a separate follow-up (not required — this slice carries it).
