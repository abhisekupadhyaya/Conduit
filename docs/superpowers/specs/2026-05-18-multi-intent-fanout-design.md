# Multi-Intent Fan-Out + Split-Echo — Design ("one messy ask becomes N independent things, and the guest sees the split")

| | |
|---|---|
| **Status** | Approved design (2026-05-18). Authored **docs-only on `main`** (zero merge risk); executed after slice 6 (`feat/conversation-answer-action`) merges — the established auth→stay→no-dispatch→staffing→spine→conv-aa cadence. **Slice 7 of the program; pairs with the relocation-subflow slice (8), which stacks on this.** |
| **Scope** | Realise the deliberately-stubbed **D35 decomposition pipeline**: `decompose → per-child classify(history) → per-child triage` (the deterministic D5/D30 mechanical triage), so a single guest message fans into **N independent child sub-requests** — each with its own issue code, routing, SLA, lifecycle, closure (fates never shared) — plus the **D36 split-echo** so the guest sees and can catch a mis-split. |
| **Source of truth** | Product decisions (D-series) — *what*; architecture decisions (AD-series) — *how it runs*; the dispatch-spine design — the routed substrate; the conversation-answer-action design — the merged predecessor this stacks on; this doc — *this slice*. |
| **Depends on** | **slice 6 merged** (`0006_conv_aa`, `down_revision='0005_dispatch'`): the conversation-window build + `history=` passthrough on `triage.classify`/`grounding.ground` + the `is_reservation_mutation` FLAG→`spine.open_escalation` branch already added to `guest/services/intake.py`. Slice 7 layers **additively on the post-slice-6 intake shape**, never the current-`main` shape. **Zero schema, zero migration** (the fan is already schema-supported: `Request` 1:N `ChildSubRequest`, per-child `WorkOrder`/`Glitch`, and `intake.submit_request` already loops `for t in triaged:`). |

## 1. Why this slice

The merged spine delivers *a request reaches a human and nothing is silently lost*; slice 6 makes the conversation cohere across turns. But the **core PRD promise (FR-2/FR-3, D35/D36) is still unbuilt**: `triage.decompose()` and `triage.triage()` are `raise NotImplementedError` on `main` *and* on slice 6 (slice 6 only added a `history=` param to `classify`; it explicitly stays single-intent and defers D35 to "its own later slice"). Today `classify()` trusts the LLM's per-message outcome wholesale and the system processes one message → one child. A guest who says *"can I get towels, my TV is broken, and what time is checkout?"* gets one tangled child instead of three independently-served things. This slice closes that gap and is the **richest multi-portal/multi-user journey in the product** (one message → a housekeeping servicer + an engineering servicer + an inline answer + a supervisor watching the fan).

It is a **low-surface slice**: 0 new endpoints, 0 new entities, 0 migration. Its weight is pure mechanism (`shared/domain/triage`) — the deliberate inverse of a big-bang.

## 2. Scope

**In:**

- Implement the pure **`triage.decompose(raw_text) -> list[str]`** (LLM-assisted split; AD11-conservative — failure yields a single conservative item, **never 0, never a silent drop**).
- Implement the pure **`triage.triage(child_text) -> TriagedChild`**: the deterministic **D5 slot-completeness + D30 objective risk rulebook** → `AUTO | CLARIFY | FLAG`. The LLM may only *raise* a rule-defined risk, never infer one from tone. Priority tier derives from the issue code's SLA preset, **never** from guest-asserted urgency (D20).
- Reorder `guest/services/intake.py` to the **post-slice-6** pipeline: build the conversation window (slice 6, unchanged) → `decompose` → per-child `classify(history=…)` → per-child `triage` → per-child route. **Preserve slice 6's reservation-mutation FLAG→spine branch and `requested_checkout` persistence verbatim.**
- **D36 split-echo (informational-only)**: `RequestOut` gains `split: bool` (server-decided: ≥2 children ⇒ echo, 1 ⇒ instant-ack — D5/D36); `ChildOut` gains `issue_label: str|None` (embed-derived-label idiom) and `outcome: str` (`auto|clarify|flag|no_dispatch`). Mis-split recovery is the **existing** per-child `cancel` + re-ask — no new endpoint.
- Each child keeps its own issue code, SLA, lifecycle, closure; one child's CLARIFY/FLAG never blocks a sibling (independent fates, D35).
- The explicitly-listed existing tests Slice 7 **updates as part of the slice** (not kept byte-identical): `tests/spine/test_e2e_journey.py` (`len(children)==1`), the multi-need cases in `test_intake_service`/`test_guest_dispatch`. A decompose test double in `tests/spine/conftest.py` keeps single-need fixtures green untouched (a single-need message decomposes to exactly 1 child).

**Out (stated seams, not omissions):**

- **D38 modify** — still cancel-only; the spine's `predecessor_child_id` stays inert for fan-out (siblings are parallel, never predecessor-linked; the relocation slice is the first real consumer of that column).
- **System-output fidelity** — the split-echo is computed at request time and **not persisted** (the conversation-answer-action seam, kept consistent). The window therefore still contains guest text + grounded answers, not the echo.
- **Mass-event / dedup / abuse** — D27, out of v1 (one trusted request per issue). Decompose splits *one* guest message; it is not an incident-fan.
- **`issue_code.origin` / the guest-catalog filter** — owned by the relocation slice (it introduces the first system-originated code). Slice 7 does **not** touch `issue_code`.
- Voice/i18n (D11/D41), out-of-band notification (D42), analytics read side (D1/D28) — inherited product boundaries; fan-out outcomes stream into the same append-only event log the deferred reader consumes.

## 3. Dependency & sequencing

Hard dependency on **slice 6 merged**. Authored docs-only on `main` now (zero merge risk). The one delicate file is `guest/services/intake.py` — touched by slice 6, 7, and 8. Slice 7's reorder layers **on the post-slice-6 intake** (window-build + reservation-mutation FLAG branch present) and preserves both. `decompose`/`triage` have **no caller but `intake`** (verified across `backend/conduit` + `backend/tests`), so implementing the two stubs cannot break a hidden consumer. **No migration.**

## 4. Decision ledger

| Area | Locked decision |
|---|---|
| Slice cut | D35 decomposition pipeline + D36 split-echo, single message → N independent children. Additive on merged slice 6. Zero schema. |
| Triage role | **Deterministic, LLM-boxed.** `decompose` (LLM-assisted split) and `classify` (LLM extraction, history-aware via slice 6) feed the **pure deterministic `triage()`** (D5 slots + D30 objective rulebook). History/LLM change only *what is extracted*; the outcome path is byte-identical (D30 signature test). |
| Tier source | Priority tier from `issue_code → SLAPreset.tier` only — **never** guest-asserted urgency (D20 signature test: "URGENT!!!" changes neither tier nor outcome). |
| AD11 degrade | `decompose` LLM-unavailable → exactly **one** conservative `clarify` child. Never 0, never a silent drop. |
| Split-echo | **Informational-only.** Server-decided `split: bool`; per-child `issue_label`+`outcome`. Mis-split recovery = existing `cancel` + re-ask. No new endpoint; D38 stays deferred. |
| Fan modelling | Reuse existing schema: siblings = children of one `Request`; per-child `WorkOrder`/`Glitch` (already unique-per-child). `predecessor_child_id` stays inert here. **No migration.** |
| Window not persisted | The echo is transient (the conversation-answer-action seam, kept consistent). |
| Test honesty | Tests asserting single-intent are **updated by this slice**, named explicitly (§11), not pretended byte-identical. A conftest decompose double keeps single-need fixtures green. |

## 5. Module ownership & layout

```
shared/domain/        triage.py         (implement decompose() + triage();
                                          classify() now: decompose → per-text
                                          classify(history) → triage. TriagedChild
                                          gains issue_label; requested_checkout
                                          field from slice 6 left as-is)
shared/integrations/  openai.py         (modify: decompose prompt; classify
                                          prompt already history-aware via slice 6)
core/                 config/settings   (optional: DECOMPOSE_* bound only if a
                                          pilot demands it — YAGNI; none added v1)
guest/services/       intake.py         (reorder on the POST-slice-6 shape:
                                          window → decompose → per-child
                                          classify(history) → triage → route;
                                          slice-6 reservation FLAG branch +
                                          requested_checkout PRESERVED)
guest/schemas/        conversation.py   (RequestOut.split; ChildOut.issue_label,
                                          .outcome — additive output)
                      requests.py       (unchanged — DispatchCardOut already
                                          per-child)
tests/                spine/conftest.py (decompose double); test_triage (expand);
                      test_intake_service; test_structural_guards (shapes);
                      test_e2e_journey (UPDATED — see §11); new multi-intent
                      e2e sentinel
frontend/             components/common/request-receipt.tsx (enrich: per-child
                                          issue_label + live status chip);
                      child-status-card.tsx (unchanged for fan; renders N)
```

No API routing change (0 new routes). No model, no migration. Identical conventions to the merged structure (`api→services→dal→shared/models`; pure mechanism in `shared/domain`; DAL add-only; service flushes; handler commits).

## 6. Data model

**No new tables, no new columns, no migration.** Asserted as a *positive guard* (§11): the `inspect(Model).columns` sets are byte-identical to slice 6 → proves Slice 7 added zero schema. The fan is expressed entirely through existing structure: `child_sub_request.request_id` (siblings share a `Request`), `work_order.child_id`/`glitch.child_id` (unique-per-child, so each sibling routes/glitches independently).

## 7. Mechanism

### 7.1 `decompose` — pure, LLM-assisted, AD11-safe
`shared/domain/triage.decompose(raw_text) -> list[str]`: asks the LLM (via `integrations.openai`) to split one message into independent need-texts. Single need → `[raw_text]`. Garbage/empty → `[raw_text]` (1 item, never 0). `LLMUnavailable` → caller (`intake`) degrades to a single conservative `clarify` child (the AD11 idiom slice 6/spine already use). Deterministic ordering. Pure (no DB/clock).

### 7.2 `triage` — the deterministic D5/D30 function
`shared/domain/triage.triage(child_text) -> TriagedChild`: slot-completeness + the objective risk rulebook (money/safety/move/mutation per D30) → `AUTO | CLARIFY | FLAG`. The LLM (via `classify`, now history-aware from slice 6) extracts slots/issue-code; `triage` decides the **outcome** from rules only. History and LLM influence extraction, never the risk decision — the **D30 invariant** (signature test §11). The existing "Resolution A" force-flag (`is_reservation_mutation` ⇒ FLAG) and slice 6's `requested_checkout` extraction are preserved unchanged.

### 7.3 Intake pipeline (post-slice-6, additive)
`guest/services/intake.submit_request`: (1) build the conversation window — *slice 6, unchanged*; (2) `texts = decompose(raw_text)`; (3) per text: `classify(text, catalog, history=window)` → `triage` → create `ChildSubRequest` (the existing loop body, now driven by decompose output); (4) per child route exactly as today — no-dispatch grounded answer / dispatch routing (C4) / SMALLTALK / CLARIFY-park / **slice 6's reservation-mutation FLAG→`spine.open_escalation` branch preserved verbatim**; (5) assemble the response with `split = len(children) >= 2` and per-child `issue_label`/`outcome`. Independent fates: a CLARIFY/FLAG child never blocks a sibling (each routes in its own loop iteration; no shared transaction state beyond the parent `Request`).

### 7.4 D36 split-echo
Purely a response shape. `≥2` children ⇒ `split=true` (the frontend renders the receipt); `1` ⇒ `split=false` (instant-ack, no receipt). The guest catches a mis-split by `cancel`-ing the wrong child and re-asking (existing endpoints; D38 modify deferred).

## 8. API surface

**Zero new endpoints.** `POST /guest/requests` — no signature change; response enriched (`RequestOut.split`, `ChildOut.issue_label`, `ChildOut.outcome` — additive output on an `extra="forbid"` schema, safe: forbid rejects unknown *input*). `GET /guest/requests` — unchanged (`DispatchCardOut` is already per-child; N siblings = N cards for free). The route/contract snapshot **must not drift** — asserted as the positive proof of zero added surface (the conversation-answer-action argument). No-`DELETE`→`405`, role gates, ambient identity (no ids in guest bodies — all new fields are output) all intact.

## 9. Journeys, flows, dataflow

### 9.1 Per-actor
- **Guest:** *"towels, TV broken, checkout?"* → one receipt: *"Logged 3 things"* with a live status chip per line; each resolves in place independently. Single-need asks are unchanged (instant-ack).
- **Servicer:** the towel child routes section-pooled (HK); the TV child routes skill-matched (ENG) as a Glitch — **two different servicers, two departments, in parallel**. Each is a normal task on the existing queue.
- **Supervisor:** the fan appears on the existing awareness stream; only a flagged/stalled child hits the decision queue, individually. No new surface.

### 9.2 Flow (walkable)
`POST /guest/requests("towels, TV broken, checkout?")` → window (slice 6) → `decompose`→3 texts → per-child `classify(history)`+`triage` → child A `HK-LINEN-TOWEL` AUTO→C4 routing (section-pooled), child B `ENG-*` problem-report→Glitch+routing (skill-matched), child C `checkout?` no-dispatch→grounded answer inline → response `{split:true, children:[A,B,C]}` → guest sees the receipt; A/B/C close on their own clocks; a B stall or C reservation-follow-up (slice 6) escalates **independently**.

### 9.3 Dataflow

| Producer | Data / event | Consumer |
|---|---|---|
| `intake` | window (slice 6) | `decompose`, `classify` |
| `decompose` | `list[str]` need-texts | per-child `classify` |
| `classify`(history) + `triage` | `TriagedChild{issue_code, outcome, issue_label, requested_checkout?}` | child rows; C4 routing / no-dispatch / slice-6 FLAG branch |
| `intake` | `RequestOut{split, children[]}` | guest receipt + per-child status cards |

**Invariants:** decompose never yields 0 / never silently drops (AD11); history+LLM feed extraction, never the risk decision (D30); siblings share only the parent `Request` (independent fates); exactly one append-only event per transition (inherited); zero new endpoints/entities/migration.

## 10. Frontend

`components/common/request-receipt.tsx` **already exists** with the D36 skeleton ("Logged N things"). Enrich it: per child render `issue_label` + a live **StatusBadge** chip (the unified monochrome taxonomy — see the relocation slice §10) + the echoed text; gate on `split`. `child-status-card.tsx` is unchanged for the fan (it already renders per-child; N siblings = N cards). **No new hooks** — `use-conversation.ts` gets additive type fields (`split`, `issue_label`, `outcome`) only. No new page, route, or shadcn primitive. The guest thread stays one calm view; the receipt is the single designed "the system understood you" moment (capped reading measure, calm tokens — no alarm).

## 11. Test bench

**Guarantee:** "pass ⇒ no manual re-check" + the inherited guarded classes (route/contract drift, response-shape, role-gap, append-only, leak sentinel, coverage ≥90). Extends the `tests/spine` savepoint-rollback bench + `fake_llm` doubles verbatim.

- **`test_triage.py` (expand 2→~20):** `decompose` — 1 need→1; multi-need→N; deterministic order; garbage→1 (never 0); `LLMUnavailable`→single clarify (AD11). `triage` — complete+low-risk→AUTO; missing slot→CLARIFY; D30 trigger→FLAG; reservation-mutation never AUTO (D24); **signature: "URGENT!!!" changes neither tier nor outcome (D20)**; **signature: history/LLM cannot raise/lower the rule outcome (D30)** — `classify(history="")` ≡ today; with history the *same* code ⇒ byte-identical outcome.
- **`test_intake_service.py`:** multi-intent → N children, fates independent (one CLARIFY doesn't block siblings); `split=true`+per-child `issue_label`/`outcome` for ≥2, `split=false` instant-ack for 1; slice-6 reservation FLAG branch + `requested_checkout` still fire under fan-out (regression); AD11 degrade → 1 conservative child.
- **`test_structural_guards.py`:** `RequestOut`/`ChildOut` parse back under `extra="forbid"` (red-on-drift); route/contract snapshot **unchanged** (zero-surface proof); **`test_migration` column-sets byte-identical to slice 6 → positive proof Slice 7 added zero schema.**
- **Tests UPDATED by this slice (named, not byte-identical):** `test_e2e_journey.py` (`len(children)==1` → multi-aware); multi-need cases in `test_intake_service`/`test_guest_dispatch`. `tests/spine/conftest.py` gains a `decompose` double so single-need fixtures stay green untouched.
- **New e2e sentinel:** one scripted 3-need journey via the real APIs + real engine — split echoed, HK-dispatch + ENG-dispatch(Glitch) + no-dispatch-answer walk independently to closure; exactly one append-only event per transition; zero residue on a deliberately-failed sub-leg (savepoint isolation).

CI: Postgres-required, full suite + coverage gate + savepoint isolation + leak sentinel; red blocks merge.

## 12. Verification bar ("done" means)

`decompose`/`triage` implemented and pure; a multi-need message fans into N independently-routed children with the split echoed; the D30 risk decision is provably unchanged by history/LLM; single-need behaviour is byte-identical (back-compat); slice-6's window + reservation FLAG branch + `requested_checkout` still work under fan-out; zero new endpoints/entities/migration (route/contract snapshot + column-sets unchanged, asserted); the named updated tests are green for the new behaviour and the full layered + inherited + e2e bench is green under savepoint isolation with zero residue on failure.

## 13. Open / deferred (named, not silent)

- **D38 modify** — cancel-only; `predecessor_child_id` inert here (the relocation slice is its first consumer).
- **System-output fidelity** — split-echo not persisted; clarify-resume coreference stays weak until a later slice persists system outputs.
- **Mass-event/dedup/abuse** — D27, out of v1.
- **`issue_code.origin` + guest-catalog filter** — owned by the relocation slice (8).
- **Analytics / voice / i18n / out-of-band** — inherited product boundaries.
