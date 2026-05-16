# Dispatch & Escalation Spine Slice — Design ("A guest's request reaches a human, and nothing is silently lost")

| | |
|---|---|
| **Status** | Approved design (2026-05-16) |
| **Scope** | The journey segment after staffing: a dispatch-mode request is routed to the accountable on-shift servicer, runs the full work-order lifecycle under two durable timers, and closes on the guest's word — with the escalation spine (stall · servicer-raised · triage-flag → time-boxed supervisor checkpoint → bounded auto-proceed → duty-manager backstop), the Glitch service-quality flow, cross-department notification, the supervisor decision queue + awareness stream, and SLA-preset / escalation-ladder configuration. This is the slice the prior four were preconditions for. |
| **Source of truth** | Product decisions (D-series) — *what*; architecture decisions (AD-series) — *how it runs*; data-model docs (`docs/datamodels/`) — *shape*; this doc — *this slice* |
| **Depends on** | Auth, stay/binding, no-dispatch (all merged), and **staffing-availability merging** (`feat/staffing-availability`: `StaffProfile`/`StaffSkill`/`Roster`/`RosterAssignment`, the pure `shared/domain/availability.effective_available` predicate this slice's routing *consumes and never re-derives*, the `tests/spine/conftest.py` savepoint-rollback harness, the `shared/events` writer, the route-contract snapshot guard, migration `0004_staffing`). Authored **docs-only now (zero merge risk)**; executed after staffing lands. Migration is the **fifth** Alembic version (`down_revision='0004_staffing'`). |

## 1. Why this slice

Slicing is by **journey segment** — every slice closes a real, demoable gap and stacks on the previously-proven substrate. Auth delivered *provisioned → login*. Stay/binding delivered *checked-in → ambient {stay,room,section}* and the one ambient-mutating event (relocation). No-dispatch delivered *guest asks → grounded answer / honest deferral* and built the intake + mechanical triage + the append-only `event` writer + the `ChildSubRequest` container. Staffing delivered *who a servicer is + when they work + are they at post* as the pure `effective_available` predicate.

Every one of those was a **precondition**. None of them lets a guest's request actually reach a human and come back resolved. The `ChildSubRequest` exists with `fulfilment_mode='dispatch'` as a triage outcome but there is **no routing, no work order, no timer, no escalation, no closure-by-confirmation, no supervisor runtime surface**. The scaffolds for the spine (`shared/domain/lifecycle.py`'s full `ChildState` enum, `shared/domain/routing.py`, `shared/engine/{runner,timers,spine,sweeper}.py`) exist as `NotImplementedError` stubs anticipating exactly this slice.

This slice closes the segment the system exists for: **a request is delivered by the right human, the lifecycle is owned end-to-end, the human supervisor is a time-boxed checkpoint that never blocks, and nothing stalls silently.** It is deliberately the largest cut so far — full dispatch *and* the escalation spine *and* the Glitch flow *and* cross-department notification *and* the supervisor decision-queue + awareness surfaces *and* SLA/ladder configuration — taken as one coherent journey so the architecture is designed whole rather than wedged together across slices. The landing risk of a big-bang cut is real and named (§3); it is an accepted, deliberate trade for journey coherence.

## 2. Scope

**In:**

- **Routing** as pure `shared/domain/routing.select(...)` — D12 housekeeping (section-pooled: positional owner → claim-fallback broadcast to in-zone staff) and D18 engineering (skill-matched → least-loaded → priority queue, P1 preempts). Consumes staffing's `availability.effective_available`; never re-derives it.
- **`WorkOrder`** lifecycle: CREATED → PUSHED|BROADCAST → ACCEPTED → IN_PROGRESS → COMPLETED(notes-only, D16); reassign mutates the assignee **in place** while the accountable owner is unchanged (D12 positional accountability).
- **Durable `Timer` engine** verbatim to AD5: rows written in the same transaction as the transition; in-process poller (`FOR UPDATE SKIP LOCKED`, DB `now()`); accept-window + fulfilment-SLA (D23), supervisor-SLA (D9), backstop-cycle (D21); the reconciliation `sweeper` + `failed_transitions`.
- **Escalation spine**: three triggers (triage-flag D5/D30, stall D10/D23, servicer-raised D20) → `Escalation` + a deterministic `Recommendation` → supervisor decision queue; supervisor approve/edit/override; **silence past supervisor-SLA → auto-proceed on the recommendation** (D9); bounded — after **N** cycles → **hard-escalate to the non-time-boxed duty manager** (D21).
- **`ChildSubRequest` closure**: full guest-confirm path — DONE_PENDING_CONFIRM → guest confirm → CLOSED; guest "no" → REOPEN; no response → stays open and ages (supervisor-visible). Cancel until Closed (D37, notifies the committed servicer).
- **Glitch** (D43/D44/D19): a `problem_report` child opens a `Glitch` riding it; visible on the awareness stream throughout; auto-closes with the underlying child; supervisor may hold open if recovery owed; `recovery_cost` a manual field (no automated comp v1).
- **`CrossDeptNotification`** first-class (D14): a `WorkOrder` COMPLETED may notify/unblock another department (engineering clears a room → housekeeping/front-desk).
- **The first event read model**: a polled projection over the append-only `event`+detail log powering the supervisor **awareness stream** (incoming · task delegation · servicer recent work · open glitches) and the **decision queue**.
- **CONFIG**: `SLAPreset` (P1–P4 accept-window / fulfilment-SLA / supervisor-SLA durations, D15) and `EscalationLadder` (path + duty manager + N-cycle bound, D21) — full supervisor CRUD on the `issue_code` CONFIG idiom; an additive `issue_code.sla_preset_id` FK (the one flagged cross-slice touch, §3).
- Portal surfaces coming alive: guest status cards + confirm/reopen/cancel; servicer Task Queue + Task Detail + raise-escalation (servicer index becomes the queue, staffing's shift+presence a compact header); supervisor decision queue, awareness stream, Task Explorer/Override (D6), SLA-preset + escalation-ladder Setup.
- The `event` taxonomy extended **additively** (work-order / escalation / glitch / timer / cross-dept event types + thin detail tables) via the merged `shared/events` writer. Migration `0005_dispatch_spine` (`down_revision='0004_staffing'`). A comprehensive backend bench extending the merged savepoint-rollback harness.

**Out (by decision, not omission — stated seams):**

- **D35 multi-intent decomposition** — single-intent only: one guest message → one `Request` → **one `ChildSubRequest`**. The Request/child split stays structurally 1:1 this slice. (`triage.decompose` stub stays unimplemented.) Stated seam.
- **D24 reservation-mutation trigger + `reservation_facts`** — the generic D30 risk-rulebook FLAG trigger is wired (the spine needs it regardless); the *specific* reservation/revenue-mutation always-flag path and the deferred `reservation_facts` table stay their own later slice. The answer↔action seam is a stated seam.
- **Guest modify (D38)** — cancel is in (D37); modify (= cancel + recreate via re-triage, predecessor lineage) is a thin sugar over intake+cancel, deferred. A nullable `predecessor_child_id` column is added as the inert seam only.
- **Analytics / bad-actor surfacing (D1/D28)** — a later read model over the same event log. The write seam is fully born here; the analytics read side is deferred (as every prior slice deferred its read side).
- **WorkOrder lineage on reassign / Glitch riding *many* children** — 1:1 with the child this slice; the *-shape re-opens with D35. Stated seam.
- **Voice / i18n / out-of-band notification (D11/D41/D42)** — inherited product boundaries; duty-manager hard-escalation surfaces **in-portal only** (no page/call ladder), consistent with AD7/D42.
- **Roster/SLA validity floors** — D31 trusts well-formed config; no "every section has an owner", no preset-coherence enforcement beyond CHECKs. Stated boundary.

## 3. Dependency & sequencing

Hard dependency on **staffing-availability merging**. This slice is authored **docs-only now (zero merge risk)** and executed after staffing lands, stacking on its merged state — the exact auth→stay/binding→no-dispatch→staffing cadence. Its migration is the **fifth** Alembic version (`down_revision='0004_staffing'`). It consumes staffing's `availability.effective_available` as an imported pure function and never re-derives the rule.

**The one deliberate cross-slice touch:** an additive `issue_code.sla_preset_id` FK (nullable, then populated) on the no-dispatch-owned `issue_code.py` — analogous to stay/binding additively extending auth's `/auth/me`. Plus the additive widening of the `child_sub_request.state` CHECK to match the **already-declared** `lifecycle.ChildState` enum, and the additive extension of the `event.type` CHECK + new detail tables via the merged writer. The route-contract snapshot **will go red** on the new routes/shapes — that is the guard working; it is regenerated **within this slice** as the conscious "I meant to change the contract" step.

**Big-bang landing risk (named, accepted).** This is ~five prior slices' worth of surface in one PR, and the first slice touching genuinely hard infra (durable crash-safe timers). Every prior spec deliberately deferred the spine; this one does not. The risk to clean landing and to merging against any in-flight sibling is real and was an explicit, informed product decision in favor of designing the journey whole. The phased internal structure (data model → engine → routing → lifecycle → spine → portals → bench) is the mitigation for *building* it incrementally even though it *lands* as one cut.

## 4. Decision ledger

| Area | Locked decision |
|---|---|
| Slice cut | Full dispatch + escalation spine + Glitch + cross-dept + decision-queue + awareness read model + SLA/ladder CRUD, **single-intent**, **big-bang one PR**. Largest cut to date; landing risk accepted for journey coherence (§3). |
| Multi-intent | **Deferred.** One message → one `Request` → one `ChildSubRequest` (1:1). `triage.decompose` stays a stub. D35 fan-out + WorkOrder-lineage + Glitch-*-shape re-open together later. |
| Routing module | **Split.** `shared/domain/routing.py` = **pure `select(...)`** (no DB; the `availability.py`/`triage.py`/`grounding.py` precedent). Effecting (create `WorkOrder`, arm timers, emit events) lives once in the shared `lifecycle` orchestrator. The stub's side-effecting `route(child_id, model)` signature is scaffolding and is replaced — stall/reassign/auto-proceed re-run the **same pure `select`**, never re-derive D12/D18. |
| Spine ownership | **Shared-owned.** All spine writes in `shared/engine` + `shared/domain/lifecycle`. Portals own only their surface: a self-scoped read DAL over shared models + a thin guard service delegating into the shared orchestrator/spine. The background engine **cannot** import a portal (Resolution E) — which is precisely why the executor must be shared. |
| One executor, two entrypoints | `supervisor/services/decisions.resolve` (human) and `engine/runner` (timer auto-proceed) both call **`shared/engine/spine.apply_recommendation`**. Silence ≡ approve is **structural**, not duplicated logic — the D9 non-blocking guarantee is by construction. |
| Lifecycle org | **Per-entity machines** (`lifecycle/{child,workorder,escalation,glitch}.py`, pure guard/transition predicates) + a **thin `lifecycle/__init__.transition()` orchestrator** that, in one transaction, applies the guarded transition + appends `event`+detail (merged writer, extended) + arms/cancels `Timer`s + performs cross-entity hops. Matches `docs/datamodels/lifecycle.md` (separate machines) + the small-bounded-module discipline. |
| Recommendation | Its **own SPINE entity** (resolves entities.md Q3 toward an entity). **Deterministic typed `action`** (auto-proceed-safe) + **templated `rationale_text`**; the LLM is an injectable seam **stubbed** in v1 (the "LLM is boxed" philosophy, D5/D30; auto-proceed never executes free-form text). Params modelled as **per-action detail tables** (the event-detail idiom: `rec_reassign`/`rec_relocate`/`rec_extend_sla`/`rec_approve`/`rec_deny`), extended additively by the writer. |
| Timer | **AD5 verbatim.** Rows in the same txn as the transition; in-process poller `WHERE state='pending' AND fire_at <= now() FOR UPDATE SKIP LOCKED`; **DB `now()`** the time source; `(state, fire_at)` index; reconciliation `sweeper` + "age of oldest unfired timer" metric; `failed_transitions` + alarm; per-timer try/except, loop never dies. Subject = **nullable typed FKs** `child_id?`/`work_order_id?`/`escalation_id?` + a CHECK that **exactly one** is set (every column a real FK; real referential integrity — replaces the stub's `(subject_type, subject_id)` string pair). |
| Timer test seam | Engine loop **disabled in tests** (the existing `s.engine_enabled` setting). Tests make timers due by setting `fire_at` **into the past** (real DB `now()` preserved — AD5 honest) and drive firing via a **test-only synchronous `engine.tick(session)`** = one claim-and-fire cycle on the test savepoint. Zero production clock seam; deterministic bench. |
| Closure / triage detail / revised_eta | State + columns **on `ChildSubRequest`** (entities.md Q3/Q5/Q8 resolved toward embedded; the no-dispatch closure-lite precedent). Full guest-confirm closure is child lifecycle states, not a separate entity. `revised_eta` a nullable column (D22). |
| WorkOrder / Glitch cardinality | `child_id` a **unique FK** on each (physical 1:1; the `staff_profile.account_id`-pk precedent). Reassign mutates `assigned_servicer_id` in place; `accountable_owner_id` never changes (D12). Glitch 1:1 child. *-shapes are stated seams (D35). |
| Child state CHECK | **Additively widened** to the full already-declared `lifecycle.ChildState` enum (`routing/pushed/broadcast/accepted/in_progress/done_pending_confirm/cancelled` added to the existing set). Additive ALTER, never a data migration — the `event.type` CHECK precedent. |
| D24 / reservation_facts | **Deferred.** Generic D30 FLAG trigger wired (spine needs it); the reservation-mutation always-flag trigger + `reservation_facts` is its own later slice; answer↔action a stated seam. |
| Events seam | New event types + thin detail tables added **additively** via the merged `shared/events.writer` (extended, never rewritten). Append-only: no app update/delete path, asserted. The first **reader** of the log (awareness/decision projections) is born here — the deferred read side, finally consumed. |
| CONFIG | `SLAPreset` + `EscalationLadder` full supervisor CRUD on the `issue_code` idiom (POST/PATCH, disable-not-delete, no `DELETE`). Additive `issue_code.sla_preset_id` FK — the single flagged cross-slice touch (§3). |
| Awareness vs decision | **Two distinct supervisor surfaces / routes** (D2 — watch-only vs act-only; not a layout choice). Both polled (AD7). One **composite** `GET /supervisor/awareness` projection; one `GET /supervisor/decisions`. |
| Layering | `api → services → dal → shared/models`; fully async; DAL add-only/no-flush/no-commit; services guard + raise domain errors + emit event + flush; API handler commits at the edge; reads never commit; ORM up, schema mapping at the API layer; engine has engine-local data access (its own background session, AD4/AD5). Identical to merged slices. |
| Errors | Merged `core/exceptions` only (`ConduitError`=400, `NotFoundError`=404, `AuthError`=401, `ForbiddenError`=403, `ConflictError`=409, `ValidationError`=422). No new exception class. |
| Deletes | **No `DELETE` anywhere → `405`, asserted** (cross-slice invariant). "Remove" = `status=disabled` / a guarded cancel transition. |
| No jsonb / no PG enums | Every column a real FK or scalar; `text + CHECK` over PG enums; recommendation params and event payloads relational. Identical to merged slices. |
| Portal ownership | `guest`/`servicer`/`supervisor` self-contained; no cross-portal DAL import (Resolution E). The shared substrate is `shared/models` + `shared/domain/*` (pure) + `shared/events.writer` + `shared/engine/*`. Intentional self-scoped read duplication (the `public/dal/bindings.py` precedent). |

## 5. Module ownership & layout

```
shared/models/        child_sub_request.py (modify: +cols, widen state CHECK)
                      work_order.py timer.py escalation.py recommendation.py
                      glitch.py cross_dept_notification.py sla_preset.py
                      escalation_ladder.py issue_code.py (modify: +sla_preset_id FK)
                      event.py (modify: extend type CHECK + new detail tables)
                      __init__.py + __all__ (firm order: event✓ → sla_preset →
                      escalation_ladder → work_order → timer → escalation →
                      recommendation → glitch → cross_dept_notification)
shared/domain/        routing.py   (implement pure select(...)→Selection; no DB)
                      recommendation.py (new, pure: trigger+context →
                                   typed action + templated rationale; LLM seam injected)
  lifecycle/          __init__.py  (orchestrator transition(): guarded txn +
                                   writer + timers + cross-entity hops)
                      child.py workorder.py escalation.py glitch.py (pure guards)
shared/engine/        runner.py sweeper.py timers.py spine.py
                      (implement: poller / reconciliation / arm-cancel /
                       open_escalation·apply_recommendation·hard_escalate;
                       engine-local data access — own background session)
shared/events/        writer.py (modify: + emit_* for the new types/details)
core/                 deps.py (reuse staffing's single Python now() helper for
                              business time; timer time stays DB now())
guest/dal/            requests.py        (self-scoped status read)
guest/services/       conversation.py    (confirm/reopen/cancel → orchestrator)
                      intake.py (modify: triage AUTO + mode=dispatch →
                                 shared routing-effect entrypoint)
guest/schemas/        requests.py        (extra="forbid")
guest/api/            requests.py        (registered in guest/api/__init__.py)
servicer/dal/         tasks.py           (self-scoped pushed+claimable read)
servicer/services/    tasks.py           (claim/accept/start/complete/raise)
servicer/schemas/     tasks.py
servicer/api/         tasks.py
supervisor/dal/       decisions.py awareness.py children.py
                      sla_presets.py escalation_ladder.py
supervisor/services/  decisions.py override.py setup.py
supervisor/schemas/   decisions.py awareness.py setup.py
supervisor/api/       decisions.py override.py setup.py
                      (all registered in supervisor/api/__init__.py)
migrations/versions/  0005_dispatch_spine.py
tests/spine/          conftest reuse + layered modules + test_e2e_dispatch.py
frontend/             (see §10)
```

API routing matches the merged structure: sub-routers carry a short prefix, composed by `<portal>/api/__init__.py`; `main.py` adds `/api`. Supervisor gate `_sup = require_roles("supervisor","duty_manager")`; servicer `require_roles("servicer")`; guest `require_roles("guest")`. All gates per-handler, server-side regardless of client.

## 6. Data model

`uuid` pk (`default uuid.uuid4`), `timestamptz` via `DateTime(timezone=True)`, **`text + CheckConstraint`** for every enum (no PG enums, no jsonb), `created_at`/`updated_at` with `func.now()`/`onupdate`, `status text+CHECK(active|disabled) server_default 'active'` on CONFIG (disable-not-delete) — the merged `issue_code.py` idiom verbatim. Registered so the **fifth** Alembic autogenerate sees them, stacked on `0004`.

### `child_sub_request` (modify — additive)
Add: `priority_tier text+CHECK(P1|P2|P3|P4)` nullable (derived from the issue code's `SLAPreset` at triage; independent of triage outcome — a P1 may be fully AUTO, D20); `closure text+CHECK(pending|confirmed|reopened|aging) ` nullable; `revised_eta timestamptz` nullable (D22); `predecessor_child_id uuid fk→child_sub_request` nullable (inert modify seam, D38 deferred). **Widen** the `state` CHECK to the full `lifecycle.ChildState` enum (additive ALTER).

### `work_order` `SPINE`
| col | type | notes |
|---|---|---|
| `id` | uuid pk | |
| `child_id` | uuid **unique** fk→child_sub_request | physical 1:1 (D35-deferred *-shape) |
| `kind` | text+CHECK`(dispatch\|human_concierge_answer)` | the one no-dispatch human-concierge exception still lands here |
| `routing_model` | text+CHECK`(section_pooled\|skill_matched)` | D12 / D18 |
| `assigned_servicer_id` | uuid fk→account nullable | mutated in place on reassign |
| `accountable_owner_id` | uuid fk→account nullable | **never changes** on claim-fallback/reassign (D12) |
| `section_id` | uuid fk→section nullable | section-pooled only (D12) |
| `priority_tier` | text+CHECK(P1..P4) | D18 P1-preempt ordering |
| `queue_position` | integer nullable | engineering skill-scarce queue (D18) |
| `state` | text+CHECK`(created\|pushed\|broadcast\|accepted\|in_progress\|completed\|cancelled)` | |
| `completion_notes` | text nullable | notes-only, no evidence burden (D16) |
| `created_at`/`updated_at` | timestamptz | |

### `timer` `SPINE` (AD5)
`id` uuid pk · `type text+CHECK(accept_window|fulfilment_sla|supervisor_sla|backstop_cycle)` · `child_id?`/`work_order_id?`/`escalation_id?` real nullable FKs · **CHECK exactly one subject FK non-null** · `fire_at timestamptz not null` · `state text+CHECK(pending|fired|cancelled) server_default 'pending'` · `cycle integer` nullable (backstop) · `created_at`. **Index `(state, fire_at)`.**

### `escalation` `SPINE`
`id` uuid pk · `child_id fk` · `trigger text+CHECK(triage_flag|stall|servicer_raised)` · `state text+CHECK(open|approved|edited|overridden|auto_proceeded|hard_escalated)` · `cycle_count integer server_default '0'` (D21 bound) · `raised_by_account_id uuid fk→account` nullable (servicer-raised) · `resolved_by_account_id uuid fk→account` nullable (null ⇒ auto_proceeded) · `created_at`/`resolved_at`.

### `recommendation` `SPINE` — base + per-action detail
Base: `escalation_id uuid pk fk→escalation` (1:1, pk-is-fk) · `action text+CHECK(reassign|broadcast|relocate|extend_sla|approve|deny)` · `rationale_text text not null` (templated; LLM seam stubbed) · `created_at`. One thin detail per action (1:1, `recommendation_escalation_id` pk fk): `rec_reassign{target_account_id fk→account}`, `rec_relocate{target_room_id fk→room}`, `rec_extend_sla{extend_seconds int}`, `rec_approve{}`, `rec_deny{}`, `rec_broadcast{}`. New action later = new detail + one CHECK value (additive — the event-detail idiom).

### `glitch` `SPINE`
`id` uuid pk · `child_id uuid **unique** fk` (1:1; *-shape D35-deferred) · `state text+CHECK(open|held_open|auto_closed|closed)` · `opened_from text+CHECK(problem_report|dispute)` · `recovery_owed boolean server_default 'false'` · `recovery_cost numeric` nullable (manual, no auto-comp — D19) · `created_at`/`closed_at`.

### `cross_dept_notification` `SPINE` (D14)
`id` uuid pk · `source_work_order_id fk→work_order` · `target_department text+CHECK(housekeeping|engineering|room_service|concierge|front_desk|runner)` · `child_id fk→child_sub_request` nullable (the child it unblocks) · `reason text` · `state text+CHECK(open|acknowledged)` · `created_at`.

### `sla_preset` `CONFIG`
`id` uuid pk · `property_id fk→property` · `tier text+CHECK(P1|P2|P3|P4)` · `accept_window_seconds int not null` · `fulfilment_sla_seconds int not null` · `supervisor_sla_seconds int not null` · `status text+CHECK(active|disabled)` · `created_at`/`updated_at`. **Partial unique** `(property_id, tier) WHERE status='active'`.

### `escalation_ladder` `CONFIG`
`id` uuid pk · `property_id fk→property` · `duty_manager_account_id uuid fk→account` · `n_cycle_bound int not null` (D21) · `status text+CHECK(active|disabled)` · `created_at`/`updated_at`. **Partial unique** `(property_id) WHERE status='active'` (one active ladder per property).

### `issue_code` (modify — additive)
Add `sla_preset_id uuid fk→sla_preset` nullable (the flagged cross-slice touch). Triage derives `child.priority_tier` via `issue_code → sla_preset.tier`.

### Event taxonomy
Extend the merged `event.type` CHECK **additively**: `work_order_created · work_order_pushed · work_order_broadcast · work_order_accepted · work_order_in_progress · work_order_completed · work_order_cancelled · child_routed · child_done_pending_confirm · child_closed_confirmed · child_reopened_by_guest · child_cancelled · escalation_opened · escalation_resolved · recommendation_created · glitch_opened · glitch_closed · cross_dept_notified · timer_fired · sla_preset_created · sla_preset_updated · escalation_ladder_created · escalation_ladder_updated`. One thin per-type detail table each (the merged stay/binding/no-dispatch precedent — kept for "every mutation emits one append-only event", which is what makes the awareness/decision read model clean; a later pass may collapse thin ones). Emitted via the **merged `shared/events.writer`, extended** — never `lifecycle.transition` re-implemented per type.

### Migration `0005_dispatch_spine`
`down_revision='0004_staffing'`; creates the new tables; `ALTER` the child `state` CHECK + `event.type` CHECK + adds `issue_code.sla_preset_id`; `upgrade→downgrade` round-trips clean; every CHECK/FK rejects; the timer exactly-one-subject CHECK rejects 0 and ≥2 FKs; the `work_order.child_id` / `glitch.child_id` unique FKs physically reject a 2nd; the SLA-preset and ladder partial-unique indexes reject a 2nd active and **allow** a disabled one.

## 7. Mechanism

### 7.1 Routing — pure `shared/domain/routing.select(...)`
No DB. Inputs: the child's `issue_code` routing model, already-fetched candidate servicers with their `StaffProfile`/`StaffSkill`/roster assignments, the current load, and `now`. Calls staffing's `availability.effective_available(profile, assignments, now)` per candidate (never re-derives it). Returns a `Selection`:

- **D12 section-pooled:** the section's positional **owner** if `effective_available`; else a **claim-fallback broadcast plan** to the in-zone `effective_available` pool. The owner is the `accountable_owner_id` regardless of who later claims.
- **D18 skill-matched:** filter to `effective_available` engineers whose `StaffSkill` matches → **least-loaded** (fewest active work orders) → on tie, queue with `priority_tier` ordering (**P1 preempts**). `accountable_owner_id` = the matched engineer.
- No eligible candidate → an empty selection with a `flag` reason → triage-flag escalation (never a silent drop).

Stall/reassign/auto-proceed call this **same function** with the stalled assignee excluded — the rule lives once.

### 7.2 Lifecycle — per-entity machines + orchestrator
`lifecycle/{child,workorder,escalation,glitch}.py` are pure: `legal(from,to) -> bool` + guard predicates. `lifecycle/__init__.transition(s, subject, to, *, actor, **ctx)` is the **only** writer path: validates legality (else `ConflictError`), applies the state change, appends exactly one `event`+detail via the merged writer, arms/cancels `Timer`s, and performs cross-entity hops in **one transaction** (caller's session; service flushes; API commits at the edge):

- `WorkOrder → completed` ⇒ child → `done_pending_confirm`; if the issue code declares a downstream department ⇒ emit `CrossDeptNotification` (D14).
- child `routed` ⇒ create `WorkOrder`, arm accept-window + fulfilment-SLA timers (D23).
- `Escalation` resolved (relocate action) ⇒ call stay/binding's merged `relocate_stay` seam (re-bind), close the Glitch with the child.

### 7.3 Timer engine — AD5 verbatim
`engine/runner._tick()`: `SELECT … WHERE state='pending' AND fire_at <= now() FOR UPDATE SKIP LOCKED LIMIT k`; per timer, in its own try/except, apply the due transition via the orchestrator + append the event + mark `fired`, commit; a failure → `failed_transitions` + alarm, loop continues. accept-window/fulfilment-SLA breach → **stall** → `spine.open_escalation(stall)`. supervisor-SLA breach → `spine.apply_recommendation(auto_proceeded)`. backstop-cycle → `spine.hard_escalate`. `engine/sweeper.sweep()`: the slower watchdog emitting "age of oldest unfired timer". DB `now()` is the only time source. Tests: `s.engine_enabled=False`, `fire_at` set into the past, explicit synchronous `engine.tick(session)`.

### 7.4 Spine — `shared/engine/spine.py`
- `open_escalation(s, child, trigger)` → `Escalation(open)` + `recommendation.build(...)` (pure, deterministic per trigger: stall → `reassign`(routing.select excluding stalled) or `broadcast`; servicer-raised "can't fix" → `relocate`(deterministic available-room lookup) or `extend_sla`; triage-flag → `approve`/`deny`) + templated `rationale_text` + arm a supervisor-SLA timer.
- `apply_recommendation(s, escalation, *, outcome)` — **the single executor.** `outcome ∈ {approved, edited, overridden, auto_proceeded}`. Edited/overridden carry a supervisor-supplied action; auto_proceeded uses the stored recommendation verbatim. Executes the typed action via the orchestrator (reassign/broadcast → routing-effect; relocate → stay/binding seam; extend_sla → re-arm; approve/deny → mutation gate). Increments `cycle_count`; if `cycle_count >= ladder.n_cycle_bound` → `hard_escalate` instead (auto-proceed disabled past the floor, D21).
- `hard_escalate(s, escalation)` → `state=hard_escalated`, surfaced to the duty manager in the decision queue as **non-time-boxed, non-auto-proceeding** (a human MUST act). In-portal only (D42/AD7).

Both `supervisor/services/decisions.resolve` and `engine/runner` call `apply_recommendation` — the human/timer symmetry is structural.

## 8. API surface

Inherited conventions: cookie session; per-handler role gate (server-side regardless of client); domain errors `404/409/422`; response schemas `extra="forbid"`, internal fields never serialized; mutating handlers commit at the edge, reads never; **no `DELETE` → `405`, asserted**. Guarded transitions are dedicated **action endpoints**, not generic PATCH (the stay/binding precedent).

**Guest** (`/api/guest/*`, `require_roles("guest")`; ambient ⇒ no IDs in bodies)
- Intake **reuses the merged no-dispatch endpoint** — triage now branches to a dispatch child; no new submit route.
- `GET /guest/requests` → `200` — status cards {state, issue label, **assigned servicer name** (D17), `revised_eta`, glitch badge}. Polled.
- `POST /guest/requests/{child_id}/confirm` → `200` → CLOSED. Not the guest's / not pending → `404`/`409`.
- `POST /guest/requests/{child_id}/reopen` → `200` → REOPEN.
- `POST /guest/requests/{child_id}/cancel` → `200` — until Closed; notifies the committed servicer (D37); already closed → `409`.

**Servicer** (`/api/servicer/*`, `require_roles("servicer")`; self-scoped)
- `GET /servicer/tasks` → `200` — pushed (owned) + claimable (in-zone broadcast) work orders + live SLA/accept-window deadlines. Polled.
- `POST /servicer/tasks/{wo_id}/claim` → `200` — claim a broadcast task (D12; `accountable_owner_id` unchanged); not claimable / not in zone → `409`/`403`.
- `POST /servicer/tasks/{wo_id}/accept|start|complete` (`{notes?}` on complete) → `200` — guarded transitions; illegal transition → `409`.
- `POST /servicer/tasks/{wo_id}/raise` (`{reason}`) → `201` — D20 servicer-raised escalation.

**Supervisor** (`/api/supervisor/*`, `_sup`)
- `GET /supervisor/decisions?status=` → `200` — open escalations + recommendation + per-action detail + supervisor-SLA countdown deadline + cycle count; duty-manager hard-escalations flagged non-time-boxed.
- `POST /supervisor/decisions/{id}/resolve` (`{action: approve|edit|override, payload?}`) → `200` — the single executor; auto-proceed runs the same `apply_recommendation` server-side (no API call). Already resolved → `409`; bad payload → `422`.
- `GET /supervisor/children?...` + `POST /supervisor/children/{id}/takeover|reassign|cancel` → `200` — D6 god-mode over any child in any state.
- `GET|POST|PATCH /supervisor/sla-presets` and `/escalation-ladder` → CONFIG CRUD, disable-not-delete (`issue_code` idiom); duplicate active tier/ladder → `409`; incoherent durations → `422`.
- `GET /supervisor/awareness` → `200` — one composite polled projection over the event log: incoming · task delegation · servicer recent work · open glitches.

**No API:** `Timer` (engine-internal), `event`+detail (write path; read **only** via the awareness/decision projections), `Recommendation` (embedded in the decision item). No `/auth/*` change.

## 9. Journeys, flows, dataflow

### 9.1 Per-actor journeys
- **Guest:** ask in plain text (the merged intake seam, now branching to dispatch) → instant ack → one **status card** per request walking `acknowledged → assigned (named servicer, D17) → on the way / in progress → done — awaiting your confirmation → closed`; on a stall, **proactively told** "running late, revised ETA" (D22); one **confirm** closes it, **"no" reopens**, no response **ages** (supervisor-visible). Cancel anytime until Closed (D37). If resolution is a relocation, the new room simply appears (stay/binding's merged re-bind — no re-login).
- **Servicer:** the index **is the Task Queue** (shift + presence a compact header reusing staffing's controls): *pushed* (owned/accountable) + *claimable* (in-zone broadcast) work orders with live SLA + accept-window countdowns. Accept → in-progress → **complete-with-notes** (D16). The honest escape hatch: **raise "can't resolve"** (D20) rather than improvise. Engineering sees a P1-preempts priority queue (D18).
- **Supervisor:** **two distinct surfaces** (D2). *Awareness stream* (watch, no action): incoming · delegation · recent work · open glitches riding throughout. *Decision queue* (act, one-tap): triage-flags, stalls, servicer-raised — each with a deterministic Recommendation + supervisor-SLA countdown; approve/edit/override; **silence past the SLA auto-proceeds** (structurally identical to approve). Plus **Task Explorer/Override** (D6 god-mode) and **SLA-preset / escalation-ladder Setup**.
- **Duty manager:** a sub-actor — after **N** auto-proceed cycles an item **hard-escalates** to a decision-queue item that is **non-time-boxed and never auto-proceeds**; a human *must* act (D21). In-portal only.

### 9.2 Flows (all fully walkable)
- **Happy path:** ask → triage AUTO (dispatch) → routing-effect creates `WorkOrder` pushed to the D12 owner (busy → claim-fallback broadcast) → accept → complete-notes → guest confirm → CLOSED. Supervisor: nothing, but the request streams across the awareness panels.
- **Glitch + relocation:** `problem_report` → triage AUTO **but P1** + **Glitch opens** (visible on awareness throughout) → D18 skill-matched engineer → **quick fix** → complete → `CrossDeptNotification` → glitch auto-closes; **or** engineer raises "can't fix" → decision queue → Recommendation `relocate(→ available room)` → approve **or** auto-proceed → stay/binding `relocate_stay` re-bind → guest confirms → Glitch + WorkOrder CLOSED (recovery cost a manual field, D19).
- **Stall → no-bottleneck → bounded backstop:** two timers start (D23) → owner doesn't accept → claim-fallback exhausts → **stall fires** → guest gets a proactive revised ETA (D22) → decision-queue Recommendation ("reassign, idle adjacent") → supervisor silent past supervisor-SLA → **auto-proceed reassigns** → if that *also* fails, repeat ≤ **N** then **hard-escalate to the duty manager** (auto-proceed disabled past the floor — D21). *This flow is the slice's reason to exist.*

### 9.3 Dataflow

| Producer | Data / event | Consumer |
|---|---|---|
| Guest intake (merged seam) | `Request` → triage → **1 `ChildSubRequest`** {issue_code, tier, mode=dispatch} | routing-effect |
| `routing.select` (pure; reads staffing `effective_available`) | `Selection` → `WorkOrder` CREATED + 2 `Timer`s | servicer queue; engine |
| Servicer task detail | claim / accept / start / complete-notes | guest status card; awareness projection; cancels accept-window timer |
| `Timer` poller (AD5) | accept-window/SLA breach → STALL; supervisor-SLA → auto-proceed; backstop → hard-escalate | spine; decision queue |
| triage-FLAG (D30) · stall · servicer-raised | `Escalation` + deterministic `Recommendation` | decision queue |
| Supervisor resolve **— or timer silence** | `apply_recommendation` (one executor) → routing/lifecycle; N cycles → duty manager | lifecycle; duty manager |
| `problem_report` child | `Glitch` opened, rides the child | awareness; auto-closes with resolution |
| `WorkOrder` COMPLETED (downstream dept) | `CrossDeptNotification` | target dept (awareness/queue) |
| every transition | append-only `event` + typed detail | **awareness-stream + decision-queue read projections (polled, AD7)** |
| Guest confirm / "no" / silence | child CLOSED / REOPEN / ages | analytics seam (deferred) |

**Invariants visible in the flow:** routing reads `effective_available`, never re-derives it; every transition is one orchestrated txn with exactly one append-only event; the human is a time-boxed checkpoint everywhere except the D21 floor; silence ≡ approve structurally (one executor); relocation re-binds via the merged stay/binding seam, never a scattered field edit; the accountable owner is invariant under claim-fallback/reassign.

## 10. Frontend

Reuse the merged uniformity layer verbatim: TanStack Query (array keys, centralized invalidation, `api` client with `credentials:"include"` + 401→logout), `data-table-shell`/`page-header`/`status-badge`/`confirm`/`empty-state`/`error-state`/`combobox-field`, supervisor desktop-first / servicer & guest mobile-first, the tightened monochrome tokens. **shadcn add-then-edit always; never re-`add` an edited component.**

- **Likely zero new shadcn** (all needed primitives present). **One composed primitive:** `components/common/countdown.tsx` — client-ticking off a **server-provided deadline** (ISO), re-synced every poll; never client-derived (the DB/server clock is truth — AD5). Reused by guest card, servicer task cards, decision queue.
- **Guest:** extend the existing `components/common/child-status-card.tsx` to the dispatch lifecycle states + named servicer (D17) + `revised_eta` line (D22) + glitch badge; dispatch children swap `closure-lite.tsx` → a full confirm/reopen control. New `use-conversation` methods (confirm/reopen/cancel). Polled.
- **Servicer:** `shell/servicer/index.tsx` becomes the **Task Queue** (the working screen) with staffing's `shift-card` + `presence-control` composed into a compact sticky header (absorbs, doesn't discard, staffing's home). Task Detail as a drill-in/`Sheet`: accept/start/complete-notes + raise-escalation. New `use-tasks` hook.
- **Supervisor:** new pages on the existing layer + the `issue-code-form-dialog` CONFIG pattern — **Decision Queue** (recommendation + per-action editable form mirroring the rec detail tables + auto-proceed countdown), **Awareness Stream** (the composite projection; *separate route* — D2), **Task Explorer/Override** (D6), **SLA Presets** + **Escalation Ladder** Setup. Nav + `App.tsx` route wiring. Hooks: `use-decisions`, `use-awareness` (polled), `use-children`, `use-sla-presets`, `use-escalation-ladder`.

## 11. Test bench

**Guarantee, stated honestly:** "pass ⇒ no manual re-check" holds for every documented behaviour **and** the guarded classes (route/contract drift, response-shape drift, role-gap, append-only violation, timer non-fire) — not a guarantee against an unspecified requirement.

**Isolation** — extends the merged `tests/spine/conftest.py` unconditional savepoint-rollback; a leak sentinel asserts all new (+ inherited) tables at baseline between tests; the FK-ordered fallback delete must never fire.

**Timer control** — engine loop disabled (`s.engine_enabled=False`); timers made due by setting `fire_at` into the past (real DB `now()` preserved — AD5 honest); firing driven by a test-only synchronous `engine.tick(session)` (one `SKIP LOCKED` claim-and-fire cycle on the test savepoint).

**Layered:**
- *Migration* — `0005.down_revision=='0004_staffing'`; up/down round-trips; every CHECK/FK rejects; timer exactly-one-subject CHECK rejects 0 and ≥2; `work_order`/`glitch` `child_id` unique rejects a 2nd; SLA-preset/ladder partial-unique rejects a 2nd active, allows a disabled.
- *Pure domain* — `routing.select` exhaustive over D12/D18 × available/busy/none/skill-miss/load-tie/P1-preempt; `recommendation.build` per trigger; each `lifecycle/*` machine's legal/illegal transition matrix.
- *Engine* — poller claims only due pending timers, `SKIP LOCKED` no double-fire, per-timer failure → `failed_transitions` + loop survives, sweeper flags overdue; cancel-on-transition.
- *DAL* — self-scoped servicer/guest reads return only the caller's rows (cross-account isolation, security-adjacent must-pass); add-only/no-flush.
- *Services* — every guard branch (claim not-in-zone, illegal transition, resolve already-resolved, CONFIG dup/incoherent); exactly one append-only event+detail per mutation.
- *API* — full ASGI stack, real per-role cookie chains, every endpoint × every documented status (happy + 401/403/404/409/422/405).

**Structural guards (inherited free + asserted):** auth-coverage meta-test auto-sweeps the new routes; route/contract snapshot regenerated as the conscious step; response parse-back through `extra="forbid"`; role×endpoint matrix; append-only guard (one event+detail per mutation, no update/delete path); no-`DELETE`→`405` sweep; the existing `--cov-fail-under=90` (unchanged).

**E2E dispatch sentinel:** one scripted test that *is* the journey — supervisor seeds SLA presets + ladder → guest asks → triage AUTO dispatch → routing to the D12 owner → (a) accept→complete→guest confirm→CLOSED; (b) **stall**: no accept, `fire_at`-past + `tick` → stall → decision queue → supervisor silent, `tick` supervisor-SLA → auto-proceed reassign → repeat ≤N → hard-escalate duty manager; (c) **glitch**: problem_report P1 → Glitch opens → engineer raises → relocate recommendation → resolve → stay/binding re-bind → Glitch + WO closed → `CrossDeptNotification` emitted. Asserts exactly one append-only event per transition, the one-executor symmetry (silence path == approve path state), and zero residue on a failing run. Time pinned via `fire_at` + explicit ticks.

**CI:** Postgres required (physical invariants + `SKIP LOCKED` can't be tested on SQLite); full suite incl. coverage gate + savepoint isolation + leak sentinel; red blocks merge.

## 12. Verification bar ("done" means)

Migration `0005` applies on staffing's merged state and round-trips; a supervisor can create SLA presets + an escalation ladder; a guest dispatch request is triaged AUTO, routed to the correct D12/D18 accountable servicer consuming staffing's `effective_available`; the WorkOrder lifecycle runs to a guest-confirmed CLOSED with "no"→reopen and no-response→aging; cancel notifies the committed servicer; two durable timers fire correctly under the `fire_at`+tick harness; a stall produces a deterministic Recommendation, the supervisor-silence path auto-proceeds via the **same executor** as approve, and the D21 bound hard-escalates a non-time-boxed duty-manager item; a `problem_report` opens a Glitch that auto-closes with its child (or holds open with a manual recovery cost); a completion can emit a `CrossDeptNotification`; the awareness stream and decision queue render from the event-log projection; every transition left exactly one append-only `event`+detail; no `DELETE` exists (`405`); the contract snapshot matches (or was consciously regenerated); the full layered + inherited + structural bench + the e2e sentinel is green under unconditional savepoint isolation with zero residue on failure.

## 13. Open / deferred (named, not silent)

- **D35 multi-intent decomposition** — single-intent this slice; re-opens WorkOrder-lineage + Glitch-*-shape together.
- **D24 reservation-mutation trigger + `reservation_facts`** — generic D30 FLAG wired; the always-flag mutation path is its own later slice (answer↔action seam).
- **Guest modify (D38)** — cancel only; `predecessor_child_id` is the inert seam.
- **Analytics / bad-actor surfacing (D1/D28)** — a later read model over the same event log; the write seam + the *first* reader (awareness/decision) are born here.
- **Out-of-band duty-manager alerting (D42)** — in-portal only; a page/call ladder is post-v1.
- **Multi-property** `property_id` denormalization (AD9) — additive when query patterns demand it.
- **Thin event detail tables** — kept for "every transition emits one event" uniformity; a later pass may collapse the redundant ones once the read models are richer.
- **Supervisor visual-system convergence** — consumes the merged tokens as-is; broader tightening is not this slice's job.
