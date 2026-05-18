# Relocation Sub-Flow — Design ("a servicer can't fix it → the supervisor moves the guest → the stay re-binds, a runner moves them, and the siblings follow")

| | |
|---|---|
| **Status** | Approved design (2026-05-18). Authored **docs-only on `main`** (zero merge risk); executed after slice 6 (`feat/conversation-answer-action`) **and** slice 7 (multi-intent fan-out) merge. **Slice 8 of the program; stacks on slice 7** (the sibling-rebind journey is only expressible once the fan exists). |
| **Scope** | Wire the deliberately-stubbed **Phase-E relocate seam** into a real cross-portal journey: a servicer-raised "can't fix" → the spine computes an **eligible comparable room** (the unbuilt selection) → it lands in the decision queue as a relocation recommendation → supervisor approve / **edit the room** / override / silent-auto-proceed → the **real `relocate_stay()`** re-binds the stay → the linked Glitch closes → a **front-office "guest move" WorkOrder** is spawned → **every still-live sibling child follows the re-bind** (only expressible because of slice 7's fan). |
| **Source of truth** | D-series (*what*) · AD-series (*how it runs*) · dispatch-spine design (the escalation→relocate substrate) · multi-intent-fanout design (slice 7 — sibling re-bind depends on it) · this doc (*this slice*). |
| **Depends on** | **slice 6 merged** (`0006_conv_aa`) + **slice 7 merged** (fan-out; zero schema). The real `relocate_stay()` exists and is prod-ready; `RecRelocate.target_room_id` FK→room **exists** (populate, not add); `recommendation.build`'s `relocate` branch + `_execute_action` relocate + `_escalation_hops` relocate + the linked-Glitch close all exist but their `stay_id`/`new_room_id`/eligible-room inputs are **Phase-E ctx-passthrough** ("not yet a built surface"). Migration **`0007_relocation_subflow`, `down_revision='0006_conv_aa'`** (slice 7 adds no migration, so 0007 chains directly on slice 6's `0006_conv_aa`). |

## 1. Why this slice

Flow 02's named-open item: relocation is referenced everywhere but the **decision surface is stubbed**. `relocate_stay()` (the re-bind) is real; the escalation→relocate→glitch-close hop is real; but the spine never *computes* a room (`ctx.get("available_room_id")` is never populated — comment: *"Phase-E wiring … not yet a built surface"*), the supervisor can't *choose* a room, the auto-proceed path has nothing deterministic to apply, and **no one physically moves the guest** (no follow-up task). This slice makes relocation a real, walkable, multi-portal/multi-user journey (servicer → supervisor → guest → runner) and, with slice 7, exercises the product's hardest cross-cutting effect: a relocation triggered by *one* child mutating the ambient room for its *siblings* (flow 02 step 8 — *"re-binds the guest account, a cross-cutting effect every other flow depends on"*).

## 2. Scope

**In:**

- A new **pure `shared/domain/room_selection.py`**: `(rooms, occupancy, current_room) -> (recommended_room, eligible_rooms[])`. **Available-only** (a room is eligible iff it has no active `Stay`), deterministic order, excludes the current room. No DB/clock (the `grounding.py`/`recommendation.py` purity contract).
- Wire `spine._assemble_context` SERVICER_RAISED to call room-selection (engine-local read off the caller's session — the established spine idiom) and `recommendation.build`'s `relocate` branch to carry the **computed `target_room_id`**, persisted on the **existing** `RecRelocate.target_room_id` at recommendation-build time → the **auto-proceed-safety invariant**: silence/auto-proceed re-applies the persisted room, never re-runs selection (the conversation-answer-action persist-at-build analog).
- Wire `_execute_action`/`_escalation_hops` relocate to resolve `stay_id` + `new_room_id` via the existing `child→Request→Stay` chain and call the **real `relocate_stay()`** + close the linked Glitch (both exist — *invoked*, not reimplemented).
- **Front-office "guest move" task**: on relocate execution, spawn one `ChildSubRequest` **reusing the triggering child's `Request`** (decision 5a; lineage via the now-consumed `predecessor_child_id`) + one `WorkOrder` `kind='relocation_move'` (decision 2; additive `ck_wo_kind` value) under a **system issue code `FO-GUEST-MOVE`** (`origin='system'`, decision 1), routed via the **existing** C4 routing path. Appears on the existing servicer queue; actioned by the existing accept/start/complete.
- **Sibling re-bind**: `relocate_stay()` mutates `stay.room_id`; every still-live sibling child re-resolves ambient room via the existing `child→Request→Stay→Room→Section` chain. Guest is **proactively told** via additive `DispatchCardOut.relocated_to` (D22).
- **Data model**: `issue_code.origin text NOT NULL DEFAULT 'guest' CHECK(origin in ('guest','system'))` (decision 1); `ck_wo_kind += 'relocation_move'` (decision 2); seed `FO-GUEST-MOVE` (`origin='system'`, idempotent); intake's guest catalog filtered to `origin='guest'` (so a system code never enters the guest classify catalog). Migration `0007_relocation_subflow` (`down_revision='0006_conv_aa'`). **`RecRelocate` unchanged** (populate-not-add — asserted).
- **Frontend**: extend `child-status-card` (`relocated_to` reassuring line); the decisions page gains a `relocate` variant — a new `common/relocation-decision.tsx` (current→proposed, eligible list, comp note, SLA countdown, Approve/Edit/Override) + `common/room-picker.tsx` (over the existing `combobox-field`); install **one** new shadcn primitive `hover-card` via `npx shadcn@latest add hover-card` (then re-token); the **unified monochrome `StatusBadge` taxonomy** cleanup; the **single-accent (decision 6a)** applied only to decision-queue **Approve** + guest **"All set"**.

**Out (stated seams):**

- **Comparable/room-type matching** — `Room` has no type/rate column; the reservation/rate/room-type model is deferred (D32/D24). v1 eligible = *available*-only, deterministic, **bounded consciously**. Rich matching is a later slice gated on that model.
- **Automated comp/billing** — no entity; comp stays a **manual field** on the existing `Glitch.recovery_cost`/`recovery_owed` (D19). No money mutation here.
- **Upgrade as a distinct mechanism** — an upgrade is mechanically a relocation; it reuses this seam (no new mechanism), per the conversation-answer-action boundary.
- **Out-of-band notice of the move (D42)**, voice/i18n, analytics read side — inherited product boundaries; the relocation streams into the same append-only event log.

## 3. Dependency & sequencing

Stacks on slice 6 **and** slice 7. The sibling-rebind journey *requires* slice 7's fan (a single-intent stay has no siblings to follow the move). Coupling, named: Slice 8 edits spine-owned files **additively** — `shared/domain/recommendation.py` (`relocate` branch carries the computed room), `shared/engine/spine.py` (`_assemble_context` SERVICER_RAISED computes via room-selection; `_execute_action` resolves `stay_id`/`new_room_id`), `shared/domain/lifecycle/__init__.py` (`_escalation_hops` relocate supplies inputs + spawns the move task). Every edit is the additive extension the spine's own comments pre-authorize ("Phase-E wiring … when supplied via ctx the real seam is invoked"). No spine behaviour rewritten; the inherited relocate tests (`test_spine.py::test_apply_recommendation_relocate_closes_glitch`, `test_e2e_dispatch.py` leg c) **stay green** — Slice 8 only *supplies* the inputs they were waiting for.

## 4. Decision ledger

| Area | Locked decision |
|---|---|
| Eligible rooms | **Available-only** (no active `Stay`), deterministic order, excludes current. No `Room` column (room-type deferred, D32). Pure `room_selection.py` (no DB/clock). |
| Auto-proceed safety | Room **computed + persisted at recommendation-build** on the existing `RecRelocate.target_room_id`. Silence/auto-proceed re-applies the persisted room — selection **never** re-runs in the auto-proceed path (D9/D30; the conversation-answer-action persist-at-build invariant). |
| Re-bind | Invoke the **real `relocate_stay()`** + close the linked Glitch (both exist). Not reimplemented. |
| Move task (decision 5a) | New `ChildSubRequest` **reusing the triggering child's `Request`**; lineage via the existing **`predecessor_child_id`** (its first real consumer). No synthetic Request, no fake guest account. |
| Move WO kind (decision 2) | `ck_wo_kind += 'relocation_move'` — additive CHECK widen (the spine's additive-ALTER idiom). Legible in queue/awareness/analytics vs a normal dispatch. |
| System code (decision 1) | `issue_code.origin` (`guest`\|`system`, default `guest`, +CHECK). Seed `FO-GUEST-MOVE` `origin='system'`. **Guest catalog filtered to `origin='guest'`** (intake only; supervisor CRUD unfiltered). |
| Comp | Manual `Glitch.recovery_cost`/`recovery_owed` (D19). No automated money. |
| API | **Zero new routes.** `GET /supervisor/decisions` `detail` (already `dict`) enriched for `relocate` (`current_room`/`recommended_room`/`eligible_rooms`); `POST …/resolve` `edit` payload variant `{new_room_id}` (already `dict|None`); `DispatchCardOut.relocated_to` additive output. |
| Migration | `0007_relocation_subflow`, `down_revision='0006_conv_aa'`. `RecRelocate` **unchanged** (populate-not-add, asserted). No new tables. |
| Frontend accent (decision 6a) | Introduce the reserved `--accent-action` for **one job only**: decision-queue Approve + guest "All set". One new primitive `hover-card` via `npx shadcn@latest add`. Unify `StatusBadge` to a monochrome taxonomy. |

## 5. Module ownership & layout

```
shared/domain/        room_selection.py  (NEW, pure: rooms+occupancy →
                                           recommended + eligible[])
                      recommendation.py  (modify: relocate branch carries the
                                           computed target_room_id)
shared/engine/        spine.py           (modify, additive: _assemble_context
                                           SERVICER_RAISED → room_selection;
                                           _execute_action relocate resolves
                                           stay_id/new_room_id; spawn move task)
shared/domain/        lifecycle/__init__ (modify, additive: _escalation_hops
                                           relocate supplies inputs + spawns
                                           the relocation_move child+WO)
shared/models/        issue_code.py      (modify: + origin col + CHECK)
                      work_order.py      (modify: widen ck_wo_kind)
                      recommendation.py  (UNCHANGED — RecRelocate populate-only)
guest/services/       intake.py          (modify: list_codes(... origin='guest'))
guest/dal/            issue_codes/ (or icdal): origin='guest' filter param
*/dal/                add-only reads: rooms-without-active-stay (property),
                                       siblings-of-stay (engine/service local)
supervisor/services/  decisions.py       (modify: populate relocate detail;
                                           handle edit {new_room_id})
seed.py               + FO-GUEST-MOVE (origin='system', idempotent)
migrations/versions/  0007_relocation_subflow.py (down_revision='0006_conv_aa')
frontend/             common/relocation-decision.tsx (NEW); common/room-picker
                      .tsx (NEW, over combobox-field); child-status-card.tsx
                      (relocated_to line); supervisor/pages/decisions.tsx
                      (relocate variant); common/status-badge.tsx (unify);
                      ui/hover-card.tsx (npx shadcn add)
tests/                test_room_selection (pure); test_recommendation
                      (relocate branch); test_spine/test_engine (executor +
                      edit + auto-proceed≡approve + move-task spawn);
                      test_migration_0007; test_structural_guards (FO-GUEST-MOVE
                      catalog-exclusion signature); test_e2e_dispatch leg c
                      (extend); cross-slice sibling-rebind e2e
```

## 6. Data model

`text + CheckConstraint` for every enum; additive `ALTER`s only; registered so the **seventh** autogenerate sees them, stacked on `0006_conv_aa`.

### `issue_code` (modify — additive)
Add `origin text NOT NULL server_default 'guest'`, `CHECK(origin in ('guest','system'))`. Nullable-free via server_default (the additive-ALTER idiom; existing rows → `'guest'`, no data migration). Read by intake's catalog build (filtered `origin='guest'`); supervisor CRUD unfiltered (sees both).

### `work_order` (modify — additive)
`ck_wo_kind` drop+recreate `kind in ('dispatch','human_concierge_answer','relocation_move')` (the `0006`/`0005` additive-CHECK idiom). No column change.

### `RecRelocate` — **unchanged**
`target_room_id` FK→room already exists. Slice 8 **populates** it (was Phase-E `ctx.get`). Asserted as a positive guard (column-set byte-identical → populate-not-add).

### Seed
`FO-GUEST-MOVE`: `origin='system'`, `fulfilment_mode='dispatch'`, `routing_model` supervisor-configurable (front-office section or runner skill), `intent_kind='service'`, `is_reservation_mutation=false`. Idempotent insert-missing (the `ensure_issue_codes` idiom — `test_seed_survives_reseed` stays green).

### Migration `0007_relocation_subflow`
`down_revision='0006_conv_aa'`. `ADD issue_code.origin` (+CHECK), widen `ck_wo_kind`, seed `FO-GUEST-MOVE`. `upgrade→downgrade` round-trips; `origin` CHECK rejects garbage; widened `ck_wo_kind` accepts `relocation_move`, still rejects garbage; existing rows survive (additive). No new tables.

## 7. Mechanism

### 7.1 `room_selection` — pure
`(rooms, occupancy, current_room_id) -> (recommended_room_id|None, eligible_room_ids[])`. Eligible = rooms with no active `Stay`, deterministic order, current excluded. Empty → `(None, [])` ⇒ `recommendation.build` falls back to the **existing** `extend_sla` (regression preserved). No DB/clock.

### 7.2 Recommendation + auto-proceed safety
`spine._assemble_context` SERVICER_RAISED reads rooms/occupancy (engine-local, caller's session) → `room_selection` → context carries `recommended_room_id` + `eligible[]`. `recommendation.build`'s `relocate` branch sets `target_room_id = recommended_room_id` (params pure-Python, deterministic; LLM only renders rationale — boxed). Persisted on `RecRelocate.target_room_id`. **Silence/auto-proceed reads the persisted `RecRelocate.target_room_id`** — selection never re-runs (D9/D30; one-executor symmetry: auto-proceeded end-state ≡ approved except `resolved_by_account_id is None`).

### 7.3 Execute + the move task
`apply_recommendation` (the single executor) → `_execute_action`/`_escalation_hops` relocate: resolve `stay_id` (via `child→Request→Stay`) + `new_room_id` (= `RecRelocate.target_room_id`, or the supervisor-edited value via the existing edited/overridden path) → call **real `relocate_stay(s, stay_id, new_room_id, actor=…)`** → close the linked `Glitch` (existing). Then spawn the **move task**: `ChildSubRequest(request_id = triggering child's request_id, predecessor_child_id = triggering child.id, issue_code = FO-GUEST-MOVE, …)` + drive C4 `routing` (the existing `_route_dispatch_child`/lifecycle path — *not* reimplemented) → a `WorkOrder kind='relocation_move'` pushed/broadcast to the front-office/runner roster. Exactly one append-only event per transition (inherited).

### 7.4 Sibling re-bind
`relocate_stay` mutates `stay.room_id`. Every still-live sibling child re-resolves ambient room through the existing `child→Request→Stay→Room→Section` chain on its next read/route — **no per-sibling write**. `GET /guest/requests` sets `DispatchCardOut.relocated_to` on a live sibling whose stay re-bound (D22 proactive). The `guest_relocated` event already exists.

## 8. API surface

**Zero new endpoints.** `GET /supervisor/decisions` — `RecommendationOut.detail` (already `dict`) for `action=='relocate'` carries `current_room`/`recommended_room`/`eligible_rooms` (service-populated; no schema-class change). `POST /supervisor/decisions/{id}/resolve` — `edit` on a relocate → `payload={"new_room_id": "<uuid>"}` (already `dict|None`; validated in the handler; unknown/occupied room → `409`/`422`; already resolved → `409`). `GET /servicer/tasks` — the move task is just another `TaskOut`. `GET /guest/requests` — `DispatchCardOut.relocated_to: str|None` additive output. Route/contract snapshot **must not drift** (positive zero-surface proof); no-`DELETE`→`405`, role gates, ambient identity intact.

## 9. Journeys, flows, dataflow

### 9.1 Per-actor
- **Servicer A (engineer):** "compressor dead, can't fix" → raise (existing D20).
- **Supervisor:** decision queue shows a **relocation card** — Room 304 → recommended 511, eligible alternatives, SLA countdown; Approve / Edit room / Override; silence auto-proceeds on the persisted room.
- **Guest:** told reassuringly the room changed; **live siblings follow** (the towel goes to 511).
- **Servicer B (runner/front-office):** a "Guest move · 304→511" task on the existing queue; accept→complete.
- **Duty manager:** inherited D21 backstop unchanged (a relocation that exhausts N cycles hard-escalates, non-time-boxed).

### 9.2 Flow (walkable, cross-slice)
Slice-7 fan `{AC child, towel child}` → AC child Glitch + ENG route → servicer raise → spine `room_selection` → `relocate(target=511)` persisted → decision queue → (a) approve / (b) silent auto-proceed [identical end-state] / (c) edit→512 → `relocate_stay` re-binds stay to 511/512 → AC Glitch closed → `relocation_move` child+WO spawned (front-office) → **the still-live towel child's ambient re-resolves to the new room**; `GET /guest/requests` shows `relocated_to` on the towel card. *This is the integration proof of the program.*

### 9.3 Dataflow

| Producer | Data / event | Consumer |
|---|---|---|
| servicer raise (existing) | SERVICER_RAISED escalation | spine `_assemble_context` |
| `_assemble_context` + `room_selection` | recommended + eligible rooms | `recommendation.build` → `RecRelocate.target_room_id` |
| supervisor resolve **— or silence** | `apply_recommendation` (one executor) | `_execute_action` relocate |
| `_execute_action`/`_escalation_hops` | `relocate_stay` re-bind; Glitch closed; `guest_relocated`; `relocation_move` child+WO | servicer queue; guest cards (`relocated_to`); awareness; deferred analytics |
| live sibling read | re-resolved ambient room | guest sibling card |

**Invariants:** selection pure & never in the auto-proceed path (persisted at build); `relocate_stay` invoked not reimplemented; exactly one append-only event per transition; siblings re-resolve with no per-sibling write; `FO-GUEST-MOVE` never enters the guest catalog (signature test); zero new endpoints/tables; `RecRelocate` populate-not-add.

## 10. Frontend

`common/relocation-decision.tsx` (NEW) — the hero decision card: a two-column **304 → 511**, `eligible_rooms` as a tight selectable list (`common/room-picker.tsx` over the existing `combobox-field`), the comp note (manual `Glitch` field), a calm-prominent `Countdown` against `supervisor_sla_deadline`, actions **Approve** (the single `--accent-action`, decision 6a) / Edit / Override. `hover-card` (installed via `npx shadcn@latest add hover-card`, then re-tokened) peeks the origin request + slice-7 siblings without leaving the queue. `child-status-card.tsx` gains a reassuring `relocated_to` line (calm token, not an alert). `decisions.tsx` routes the `relocate` action to the new card; all other actions keep the existing compact row. **Cleanup (scoped):** promote `status-badge.tsx` to one **monochrome** taxonomy (every child/WO/escalation/glitch state + P1–P4 → `{label,tone}`; P1 = weight + a 2px left rule, never red) used by guest receipt, servicer queue, decision queue, awareness, task-explorer; uniform skeleton/empty/error trio on every polled surface; fixed lucide icon vocabulary (split/move/glitch/escalation/countdown). **No new hooks** — `use-decisions`/`use-conversation` get additive types; the move task rides the existing `use-tasks`; reuse the existing `use-rooms` if a supervisor picks beyond the eligible list. No new route/page.

## 11. Test bench

**Guarantee:** "pass ⇒ no manual re-check" + inherited guards (route/contract drift, response-shape, role-gap, append-only, leak sentinel, coverage ≥90, AD11 degrade). Extends the `tests/spine` savepoint bench + `fake_llm` verbatim; timers `fire_at`-past + synchronous `engine.tick`.

- **`test_room_selection.py` (NEW, pure):** available-only (excludes active-stay rooms); deterministic pick; excludes current; empty → `(None,[])` → `extend_sla` fallback (regression); asserts no DB/clock (purity).
- **`test_recommendation.py`:** SERVICER_RAISED + eligible → `relocate{target_room_id=pick}` (params not LLM); none → `extend_sla` (regression); rationale stub-rendered (boxed).
- **`test_spine.py`/`test_engine.py`:** `open_escalation` persists computed `RecRelocate.target_room_id` (not `ctx.get`); approve → `relocate_stay` re-bind + Glitch closed + one `guest_relocated`; **edit `{new_room_id}`** → re-bind to chosen (occupied/unknown → 409/422); override/deny → no re-bind/no event; **silence/auto-proceed ≡ approve** using the persisted room (signature); **move task**: exactly one `relocation_move` child (`predecessor_child_id`=trigger, same `request_id`) + WO, one append-only event, on the existing servicer queue; D21 bound holds; already-resolved → 409. Inherited `test_apply_recommendation_relocate_closes_glitch` + `test_e2e_dispatch` leg c **green unchanged**.
- **`test_migration_0007.py`:** `down_revision=='0006_conv_aa'`; `issue_code.origin` present, CHECK accepts `guest`/`system`, rejects garbage, default `guest`, existing rows survive; `ck_wo_kind` accepts `relocation_move`, rejects garbage; **`RecRelocate` column-set byte-identical (populate-not-add proof)**; up/down round-trips.
- **`test_structural_guards.py`:** **signature — `FO-GUEST-MOVE` seeded idempotently AND excluded from the guest triage catalog** (intake `origin='guest'`); supervisor issue-code CRUD/`test_issue_codes`/`test_seed_survives_reseed` green unchanged; `DecisionOut.detail` relocate fields + `DispatchCardOut.relocated_to` parse back under `extra="forbid"`; route/contract snapshot unchanged.
- **Cross-slice e2e (the integration proof — needs slice 7):** `{AC,towel}` fan → AC relocates the stay → towel sibling's ambient re-resolves → `GET /guest/requests` shows `relocated_to` on the live towel card; one append-only event per transition; zero residue on a failed leg.

CI: Postgres-required; full suite + coverage gate + savepoint isolation + leak sentinel; red blocks merge.

## 12. Verification bar ("done" means)

`room_selection` pure; servicer-raised "can't fix" yields a deterministic relocation recommendation with a computed, **persisted** room (LLM never in the auto-proceed path); approve / edit-room / override / silent-auto-proceed all drive the **real `relocate_stay()`** identically via the single executor, the linked Glitch closes, a `relocation_move` task spawns on the existing servicer queue, and (with slice 7) every live sibling re-resolves to the new room with the guest proactively told; migration `0007` round-trips on slice-6's `0006_conv_aa`; `RecRelocate` proven populate-not-add; `FO-GUEST-MOVE` proven excluded from the guest catalog; zero new endpoints/tables (route/contract snapshot unchanged); the inherited relocate tests stay green and the full layered + structural + cross-slice e2e bench is green under savepoint isolation with zero residue on failure.

## 13. Open / deferred (named, not silent)

- **Comparable/room-type matching** — available-only v1; gated on the deferred reservation/rate/room-type model (D32/D24).
- **Automated comp/billing** — manual `Glitch` field only (D19).
- **Upgrade** — reuses this seam (no new mechanism).
- **Out-of-band move notice (D42)**, voice/i18n, analytics read side — inherited boundaries.
- **Multi-stay / concurrent-relocation contention** — single trusted request per issue (D27); not modelled in v1.
