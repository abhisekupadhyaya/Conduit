# Staffing & Availability Slice — Design ("The operation is staffed, and people declare presence")

| | |
|---|---|
| **Status** | Approved design (2026-05-16) |
| **Scope** | The journey segment after no-dispatch: the supervisor declares the operational staffing structure (who someone is professionally + when they work), and the servicer declares presence — producing the exact data the next slice's routing reads (D12 section owner/backup, D18 engineering skills, D39 availability). The last precondition before dispatch; the first slice that makes the servicer portal do real work. |
| **Source of truth** | Product decisions (D-series) — *what*; architecture decisions (AD-series) — *how it runs*; data-model docs — *shape*; this doc — *this slice* |
| **Depends on** | Auth (merged), stay/binding (merged: `Property`/`Section`/`Room`, the `event` base + per-type-detail idiom, ambient resolution, the supervisor uniformity layer), and **no-dispatch merging** (the savepoint-rollback `tests/spine/conftest.py`, the `shared/events` append-only writer, the `issue_code.py` CONFIG idiom, the `issue-codes.tsx` page pattern, the supervisor CRUD hook pattern). Authored docs-only now (zero merge risk); executed after no-dispatch lands. Migration is the **fourth** Alembic version (`down_revision='0003_nodispatch'`). |

## 1. Why this slice

Slicing is by **journey segment** — every slice closes a real, demoable gap and stacks on the previously-proven substrate. Auth delivered *provisioned → login*. Stay/binding delivered *checked-in → ambient {stay,room,section}*. No-dispatch delivered *guest asks → grounded answer / honest deferral*. Every dispatch journey's precondition is *"route to the accountable on-shift servicer"* — but the system has **no concept of a servicer's profession, no roster, and no presence**. A servicer `Account` exists (auth) and `Section`/`Room` exist (stay/binding), but nothing connects a person to a section, a shift, or an availability state.

This slice closes exactly that segment, and **only** that segment: the supervisor declares the staffing structure (D13 — "structure is the hotel's, configured"), and the servicer declares presence (D39). It is the **last precondition before dispatch**, and the **first slice to bring the servicer portal alive**. It deliberately builds the derived **availability predicate** as pure shared domain — the single load-bearing artifact the next slice's routing consumes (never re-derives). The slice's whole purpose, in one module: `shared/domain/availability.effective_available(...)`.

Stay/binding named this slice as its own explicit deferral: *"`staff_profile` / roster / skills / availability — the routing slice (next; D12/D18/D39)."* This is that slice.

## 2. Scope

**In:**

- `StaffProfile` (CONFIG, 1:1 with `Account` where `role != guest`; **supervisor POST-create + PATCH-edit**, disable-not-delete) — `staff_class` (D4), `presence` + `presence_set_at` (D39, shift-scoped), `status`.
- `StaffSkill` (relational, the no-jsonb hardening of the schema-draft's `skills jsonb`, D18) — **the one sanctioned hard-replace-set entity** (named exception, §4).
- `Roster` (CONFIG, time-bounded window; resolves the `entities.md` OPEN item toward time-bounded rows — **no `Shift` entity**, D40/D31) and `RosterAssignment` (`section_id` nullable — the D12/D18 shape split; `assignment ∈ {owner,backup,member}`, D12 positional accountability).
- The **derived, never-stored** predicates: `on_shift` and `effective_available`, as a pure `shared/domain/availability.py` module — consumed by the servicer home this slice, by routing next slice.
- Supervisor **Staff** page (set class/skills/disable on existing servicer accounts) and **Rosters** page (windows + assignments, side-Sheet master-detail).
- Servicer portal coming alive: a single calm **home** screen (identity + derived shift + the one presence control), replacing the stale speculative `servicer/index.tsx`.
- The generic `event` taxonomy extended **additively** (`staff_profile_created/updated`, `staff_skills_set`, `roster_created/updated`, `assignment_created/updated`, `presence_changed`) — write-only this slice, emitted via the `shared/events` writer directly (not `lifecycle.transition` — §4).
- Migration `0004_staffing` (stacked on `0003_nodispatch`). A comprehensive backend test bench with unconditional savepoint-rollback (§11).

**Out (by decision, not omission — stated seams):**

- **All routing / dispatch** (D12/D18 selection, `WorkOrder`, accept/progress/complete) — this slice *produces* the data routing reads; it consumes none of it. The immediate next slice.
- **Timers / stall / escalation spine** (D9/D10/D23) — no timers here.
- **`Account` model changes** — `StaffProfile` is a *new* 1:1 side table; zero cross-slice edits to auth-owned `account.py` (the no-dispatch zero-auth-touch precedent).
- **Roster validity enforcement** — D31 trusts well-formed config; no "every section must have an owner" floor, no window-overlap rejection. Stated boundary, not silent.
- **Shift-change handover** (D40) — manual, out-of-system, by decision. Roster windows may abut; no handover object.
- **Generic event read model / awareness stream / analytics** — the write seam is born here; the read side is deferred (the evolution seam, exactly as every prior slice deferred it).
- **Servicer self-service of class/skills** — supervisor-owned (operational structure, D13); the servicer owns only `presence` (D39).
- **Seed** — this slice seeds *nothing* (profiles are per-account supervisor-created; rosters are pure operator data). There is no `ensure_*` idempotency concern (unlike no-dispatch). Stated as a deliberate non-thing.
- Voice / i18n / out-of-band notification (D11/D41/D42) — inherited product boundaries, unchanged.

## 3. Dependency & sequencing

Hard dependency on **no-dispatch merging**: the savepoint-rollback `tests/spine/conftest.py`, the `shared/events` append-only writer, the `issue_code.py` CONFIG idiom, the merged `issue-codes.tsx` page + supervisor CRUD hook pattern, and the tightened design tokens. This slice is authored **docs-only now (zero merge risk)** and **executed after no-dispatch lands**, stacking on its merged state — the same cadence auth→stay/binding→no-dispatch used. Its migration is the **fourth** Alembic version (`down_revision='0003_nodispatch'`). **Zero auth-owned / cross-slice code changes** to backend models; the one deliberate cross-file touch is the servicer-portal rebuild (§10 / §4 ledger), which this slice *owns into existence*. Only the route-contract snapshot regenerates (intentionally — §4, §11).

## 4. Decision ledger

| Area | Locked decision |
|---|---|
| Slice cut | Staffing structure + servicer presence only. Routing/dispatch/timers are stated seams. Thinnest cut that genuinely satisfies the D12/D18/D39 routing precondition. |
| Roster model | **B — time-bounded `Roster` rows** (`shift_start`/`shift_end`), **no `Shift` entity**. Resolves the `entities.md` OPEN ("shift explicit vs time-bounded rows") in the schema-draft's own direction; stays inside D40 (handover manual/out-of-system) and D31 (trust valid config). A first-class Shift entity would over-model against the thin-cut + no-jsonb discipline the merged code proves is house style. |
| Availability decomposition | Availability is **not one enum**. `on_shift` = *derived* from the roster window (never stored — storing it lets it drift from the roster, the anti-cache discipline of ambient re-resolution). Manual `presence ∈ {working,on_break,off}` is stored on `StaffProfile`. `effective_available` = `on_shift ∧ profile.active ∧ ¬(presence∈{on_break,off} ∧ presence_set_at ∈ current_window)` — a computed predicate, not a column. |
| Presence default (D39-literal) | **Default Working when on-shift.** D39 says "manual on-break/**off** toggle" — the toggle marks *un*availability; defaulting present-when-on-shift is the literal reading, not a divergence. **Accepted cost (named, not silent):** a servicer rostered but physically absent who forgot to toggle Off is routable until a later-slice stall surfaces it — consistent with D31 + the stall safety net; an optimistic-presence assumption the spine self-heals, never a silent wrong-dispatch. |
| Presence shift-scoping | Locking the toggle off-shift (UX) + the Working default forces presence to be **shift-scoped**: a toggle counts only while `presence_set_at ∈ current_window`; outside it, presence reads as the Working default. One column + one timestamp; the derivation does the scoping; no per-shift presence table. Yesterday's "Off" never bleeds into today. |
| Off-shift presence lock | A real **server gate**: `PUT /servicer/presence` off-shift → `409` (not merely a disabled UI control — "server-side regardless of client", the locked convention). |
| Assignment model | Supervisor assigns (D13 — single writer; servicer's only write is presence). `section_id` **nullable**. DB-CHECK: `assignment in (owner,backup) ⇒ section_id IS NOT NULL` (D12 positional accountability needs a post). Service-layer `422` (cross-table, not a CHECK): engineering account ⇒ `section_id` must be NULL (D18 skill-matched, not section-pooled). |
| Assignment cardinality | **Partial unique index** `UNIQUE(roster_id, section_id) WHERE assignment='owner' AND status='active'` — physically guarantees D12's one accountable owner per section per shift. **No per-account uniqueness** — a servicer may own one section and back up another (D12's in-zone backup pool is real ops). "Always an owner present" stays D31-trusted, not enforced. |
| Skills named exception | `StaffSkill` is the **one sanctioned hard-replace** in the codebase: `PUT /staff/{id}/skills` rewrites the row set; removed rows hard-deleted **at the DAL layer** (never an HTTP `DELETE` — the 405 invariant is untouched). Justified: skill rows are pure routing config, **not** FK-referenced by spine/provenance/the future read model (unlike `IssueCode`), so the disable-not-delete audit rationale does not apply. Scoped, asserted: a structural guard proves nothing else hard-deletes. |
| Profile verb shape | Strict `issue_code` CONFIG idiom: `POST /staff/{account_id}/profile` (201; 409 if exists; 422 if not a servicer) + `PATCH` (class/status). `GET /staff` returns `profile` **nullable** — an un-profiled servicer account is a first-class state ("provisioned, not yet profiled"). |
| Events seam (two halves) | Config mutations **do NOT** go through `lifecycle.transition` (that is the *child* state machine — no-dispatch's). Staffing entities have a `status`, not a SPINE lifecycle. Services emit events by calling the **`shared/events` append-only writer directly** — reusing half (b) of the locked seam (the writer) without forcing half (a) (the child state machine) onto config rows. Stated so no one retrofits a state machine onto a roster. |
| Predicate home | `shared/domain/availability.py` — **pure, no DB** (the `triage.py`/`grounding.py` precedent). Servicer home calls it this slice; routing calls the *same function* next slice. Single source of the rule; unit-tested in isolation. The alternative (a servicer/services helper) would force a Resolution-E-forbidden cross-portal import or duplicate the one invariant routing depends on. |
| Time source (test honesty) | Business-meaningful time (`presence_set_at`, the on-shift comparison reference) is **Python-sourced from one call site** (`freezegun`-controllable); audit time (`created_at`/`updated_at`) stays DB `func.now()`. `freezegun` freezes Python `now()` not Postgres `now()`; this split makes the chosen library honest (no Python/DB skew on anything load-bearing) and boundary tests trivial. |
| Contract snapshot friction | An intentional API change **requires regenerating the committed route/schema snapshot** — a conscious "yes, I meant to change the contract" step. This friction *is* the guarantee: unintended contract drift cannot merge silently. Accepted. |
| Cleanup scope | Servicer stale-file rebuild is **in-scope** (this slice owns the servicer portal into existence): the speculative `servicer/index.tsx` + `use-servicer.ts` (they pre-build an unbuilt dispatch queue with off-pattern hand-rolled states + inconsistent `rounded-xl`) are replaced by the real home. A supervisor tightening micro-sweep (drift-only, zero behaviour change) rides in its **own isolated commit** (the no-dispatch isolated-style-commit precedent) — uniformity without scope creep. |
| No jsonb / no PG enums | Every column a real FK or scalar; `text + CHECK` over PG enums; skills relational. Identical to merged auth/stay-binding/no-dispatch. |
| Deletes | **No `DELETE` anywhere → `405`, asserted** (cross-slice invariant). Supervisor "remove" = `status=disabled`. The `StaffSkill` DAL replace is the single scoped exception above. |
| Layering | `api → services → dal → shared/models`; fully async; DAL add-only/no-flush/no-commit; services guard + raise domain errors + emit event + flush; API handler commits at the edge; reads never commit; ORM up, schema mapping at the API layer only. Identical to merged slices. |
| Errors | Merged `core/exceptions` (`ConduitError`=400, `NotFoundError`=404, `AuthError`=401, `ForbiddenError`=403, `ConflictError`=409, `ValidationError`=422). No new exception class. |
| Portal ownership | Supervisor owns staff/roster via `supervisor/dal`+`services`; servicer owns its own reads + presence via self-scoped `servicer/dal`+`services` (no `supervisor/dal` import — Resolution E). The `shared/domain/availability` predicate + the `shared/events` writer are the deliberate shared substrate. |

## 5. Module ownership & layout

```
shared/models/        staff_profile.py staff_skill.py roster.py roster_assignment.py
                      event.py (modify: extend CHECK + add 8 detail classes)
                      __init__.py + __all__ (firm order: event✓ → staff_profile → roster)
shared/domain/        availability.py (new: pure on_shift / current_window /
                      effective_available; no DB; the substrate the slice exists for)
shared/events/        (reuse merged writer — no change)
core/                 deps.py (add: a single Python `now()` call site / time source helper)
supervisor/dal/       staff.py rosters.py
supervisor/services/  staff.py rosters.py
supervisor/schemas/   staff.py roster.py   (extra="forbid")
supervisor/api/       staff.py rosters.py  (registered in supervisor/api/__init__.py)
servicer/dal/         self.py              (self-scoped; no supervisor import — Res. E)
servicer/services/    home.py presence.py
servicer/schemas/     home.py              (extra="forbid")
servicer/api/         self.py              (registered in servicer/api/__init__.py)
conduit/seed          (no change — this slice seeds nothing, stated)
migrations/versions/  0004_staffing.py
tests/spine/          conftest reuse + layered modules + test_e2e_staffing.py
frontend/             (see §10)
```

API routing matches the merged structure: sub-routers carry a short prefix, composed by `<portal>/api/__init__.py`; `main.py` adds `/api`. Supervisor gate per-handler `_sup = require_roles("supervisor","duty_manager")`; servicer gate `require_roles("servicer")`.

## 6. Data model

`uuid` pk (`default uuid.uuid4`), `timestamptz` via `DateTime(timezone=True)`, **`text + CheckConstraint`** for every enum (no PG enums, no jsonb), `created_at`/`updated_at` with `func.now()`/`onupdate`, `status text+CHECK(active|disabled) server_default 'active'` (disable-not-delete) — the merged `issue_code.py` idiom, verbatim. Registered so the **fourth** Alembic autogenerate sees them, stacked on `0003`.

### `staff_profile` `CONFIG` — 1:1 with account
| col | type | notes |
|---|---|---|
| `account_id` | uuid **pk** fk→account | pk-is-the-fk = the 1:1 physical invariant (the `no_dispatch_resolution.child_id`-pk precedent — DB physically rejects a 2nd profile) |
| `staff_class` | text+CHECK`(housekeeping\|engineering\|room_service\|concierge\|runner)` not null | D4 |
| `presence` | text+CHECK`(working\|on_break\|off)` not null server_default `working` | D39 |
| `presence_set_at` | timestamptz **nullable** | null = never toggled; counts only if ∈ current window (shift-scoping) |
| `status` | text+CHECK`(active\|disabled)` server_default `active` | disable-not-delete |
| `created_at`/`updated_at` | timestamptz | DB `func.now()`/`onupdate` (audit; not business time) |

### `staff_skill` — relational (no-jsonb hardening, D18)
`account_id` fk→account · `skill` text not null · **composite pk `(account_id, skill)`** (the `nd_provenance_kb` composite-pk precedent — physically rejects a dup skill per account). **No `status`** — the named-exception replace-set entity (§4); rows hard-replace at the DAL.

### `roster` `CONFIG` — time-bounded window (no `Shift` entity)
`id` uuid pk · `property_id` fk→property (single-property AD9, modeled not assumed) · `shift_start`/`shift_end` timestamptz not null · **CHECK `shift_end > shift_start`** · `status text+CHECK(active\|disabled)` · `created_at`/`updated_at`. **No overlap rejection** (D31 — stated seam).

### `roster_assignment`
`id` uuid pk · `roster_id` fk→roster · `account_id` fk→account · `section_id` fk→section **nullable** · `assignment` text+CHECK`(owner\|backup\|member)` · `status text+CHECK(active\|disabled)` · `created_at`/`updated_at`.
- **DB CHECK:** `assignment in ('owner','backup') ⇒ section_id IS NOT NULL` (D12).
- **DB partial unique:** `UNIQUE(roster_id, section_id) WHERE assignment='owner' AND status='active'` (D12 — one accountable owner per section per window).
- **Service `422` (cross-table):** engineering account ⇒ `section_id` must be NULL (D18).

### Event taxonomy
Extend the merged `event.type` CHECK **additively**: `staff_profile_created · staff_profile_updated · staff_skills_set · roster_created · roster_updated · assignment_created · assignment_updated · presence_changed`. One thin per-type detail table each (`event_id` pk fk→event + the typed fk). *Honest note (the stay-binding/no-dispatch precedent verbatim):* these detail tables are thin; kept so "every mutation emits one append-only event" uniformity holds, which is what makes the deferred read model a clean read model. A later pass may collapse them; not now. Emitted via the `shared/events` writer directly (§4 — not `lifecycle.transition`).

### Migration `0004_staffing`
`down_revision='0003_nodispatch'`; creates the 4 tables + `ALTER` the event CHECK; `upgrade→downgrade` round-trips clean; every CHECK/FK rejects; `staff_profile.account_id`-pk physically rejects a 2nd profile; `staff_skill` composite-pk rejects a dup skill; the partial-unique owner index rejects a 2nd active owner for `(roster,section)` **and allows** a disabled one + the same person owning elsewhere.

## 7. The derivation (mechanism)

`shared/domain/availability.py` — **pure, no DB, deterministic**; takes already-fetched rows + an explicit `now`:

- `current_window(assignments, now) -> Roster | None` — the active roster window the account is assigned to at `now` (`now ∈ [shift_start, shift_end)`, assignment + roster `status='active'`).
- `on_shift(assignments, now) -> bool` — `current_window(...) is not None`.
- `effective_available(profile, assignments, now) -> bool`:
  ```
  w = current_window(assignments, now)
  if w is None or profile.status != 'active':         return False
  if profile.presence in ('on_break','off') and \
     profile.presence_set_at is not None and \
     w.shift_start <= profile.presence_set_at < w.shift_end:  return False
  return True                                          # Working default (D39-literal)
  ```

This is the entire load-bearing logic of the slice, in one pure testable function. The next slice's routing imports and calls it; it never re-derives the rule.

### The flow

```
Supervisor (config):
  POST /supervisor/staff/{account_id}/profile {staff_class}
    └ guard account exists(404)/role=servicer(422)/no profile(409)
    └ insert StaffProfile; event staff_profile_created; flush; commit at edge
  PUT  /supervisor/staff/{account_id}/skills {skills:[...]}
    └ guard profile exists(404); DAL replace-set (the one sanctioned hard-replace)
    └ event staff_skills_set; flush; commit
  POST /supervisor/rosters {shift_start,shift_end}      ── shift_end<=start ⇒ 422
  POST /supervisor/rosters/{id}/assignments {account_id,section_id?,assignment}
    └ owner/backup w/o section ⇒ 422 (also DB CHECK); engineering+section ⇒ 422 (D18)
    └ dup active owner ⇒ partial-unique IntegrityError ⇒ 409
    └ event assignment_created

Servicer (presence):
  GET /servicer/home
    └ self-scoped DAL: own profile + skills + assignments(+section)
    └ availability.current_window / effective_available (pure, now = Python clock)
    └ compose ServicerHomeOut (derived; no event; no commit)
  PUT /servicer/presence {presence}
    └ guard on-shift via current_window; none ⇒ 409 (server lock)
    └ DAL set presence + presence_set_at = now (Python clock call site)
    └ event presence_changed; flush; commit
```

## 8. API surface

Inherited conventions: cookie session; per-handler role gate (server-side regardless of client); domain errors `404/409/422`; response schemas `extra="forbid"`, internal fields never serialized; mutating handler commits at the edge, reads never; **no `DELETE` → `405`, asserted**.

**Supervisor — Staff** (`/api/supervisor/staff`, `_sup`)
- `GET /staff?status=&class=` → `200 StaffOut[]` — **all `role=servicer` accounts**, `profile` **nullable** (un-profiled is first-class). Account internals (`secret_hash`…) never serialized — asserted by the parse-back guard.
- `GET /staff/{account_id}` → `200 StaffOut`; not a servicer / missing → `404`.
- `POST /staff/{account_id}/profile {staff_class}` → `201`; profile exists → `409`; not `role=servicer` → `422`; missing account → `404`.
- `PATCH /staff/{account_id}/profile {staff_class?,status?}` → `200`; no profile → `404`. `status=disabled` is the "remove".
- `PUT /staff/{account_id}/skills {skills:[...]}` → `200` (replace-set, the named exception); no profile → `404`.

**Supervisor — Rosters** (`/api/supervisor/rosters`, `_sup`)
- `GET /rosters?status=&active_at=` → `200 RosterOut[]`.
- `POST /rosters {shift_start,shift_end}` → `201`; `shift_end<=shift_start` → `422`. No overlap rejection (D31 — stated).
- `PATCH /rosters/{id} {shift_start?,shift_end?,status?}` → `200`; missing → `404`; bad window → `422`.
- `GET /rosters/{id}/assignments` → `200 AssignmentOut[]`.
- `POST /rosters/{id}/assignments {account_id,section_id?,assignment}` → `201`; non-servicer / disabled-profile → `422`; `owner|backup` without `section_id` → `422`; engineering account with `section_id` → `422` (D18); duplicate active owner for `(roster,section)` → `409`.
- `PATCH /rosters/{id}/assignments/{id} {section_id?,assignment?,status?}` → `200`.

**Servicer — self** (`/api/servicer/*`, `require_roles("servicer")`)
- `GET /servicer/home` → `200 ServicerHomeOut{profile{class,skills,status}, current_shift?{window,section?,role}, next_shift?, presence, presence_locked, effective_available}` — one composed derived read; `current_shift`/`effective_available` computed live (never stored). Separate from `/auth/me` → zero auth-owned change.
- `PUT /servicer/presence {presence:"working|on_break|off"}` → `200 ServicerHomeOut`; **off-shift → `409`** (server lock; UI lock cosmetic). Sets `presence` + `presence_set_at = now()` (Python call site), emits `presence_changed`.

**No API:** `event` + detail (write-only; read model deferred — the evolution seam); guest (nothing this slice); routing (the next slice — consumer of all the above). **No `/auth/me` / auth-owned change.**

## 9. Journeys, flows, dataflow (the LanceLive idiom)

### 9.1 Per-actor journeys

- **Supervisor:** login → **Staff** (set class/skills on the auth-provisioned servicer accounts; disable = non-routable, reversible) → **Rosters** (create time-bounded windows; assign housekeeping owner/backup to a section, engineering to no section) → structure exists; **nothing dispatches — the consumer is the next slice (stated seam)**. `duty_manager` shares the gate, no distinct journey, no `StaffProfile`.
- **Servicer (the portal comes alive):** login → home shows *who you are* (class + skills) and *your shift* (derived: window · section · role, or "No active shift" + next) → the one control: presence Working/On-break/Off (D39), default Working when on-shift, **locked off-shift**. They are now observable as effective-available — *when* the next slice's routing looks.
- **Guest:** no journey by design — no guest surface.

### 9.2 Flows

- **Flow 0 — the staffing spine (cross-portal):** supervisor sets Maria `class=housekeeping`, rosters her `owner` of Section 3 for a window → Maria logs into the newly-live servicer portal, sees exactly that, toggles `presence=Working` → the system can now *compute* "Maria is effective-available for Section 3 now." The flow **ends at that observable predicate** — the routing consumer is the next slice (honest seam, the no-dispatch "parked child, no consumer" precedent).
- **A · structure the floor:** create window → owner+backup to a section → engineer with skills, no section. Events `roster_created`, `assignment_created`×N, `staff_profile_created`/`staff_skills_set`.
- **B · presence beat:** mid-shift Working → On-break → Working. `presence_changed`×3; `effective_available` flips with it (derived, live).
- **C · off-shift proof:** rostered 08:00–16:00, opens portal 20:00 → "No active shift"; presence locked; even a stale Working has no effect (not on-shift). Proves the decomposition is real.
- **D · disabled staff:** supervisor disables the profile → non-routable even if rostered+Working (status gate); re-enable restores; audit-retained.
- **E · relocation interplay (cross-slice honesty note):** roster assignments reference **Section**, not Room; stay/binding's guest relocation re-binds a *guest's room*, never a roster. Stated so the seam between slices is explicit.

### 9.3 Dataflow

| Producer | Data | Consumer |
|---|---|---|
| Supervisor · Staff editor | `StaffProfile{class,status}` + `StaffSkill[]` | servicer home (own profile); **(future) routing class/skill match D4/D18 — seam** |
| Supervisor · Rosters editor | `Roster{window,status}` | `on_shift` derivation; servicer home ("my shift") |
| Supervisor · Rosters editor | `RosterAssignment{account,section?,role}` | servicer home ("my section/role"); **(future) D12 owner/backup selection — seam** |
| Servicer · presence toggle | `StaffProfile.presence`+`presence_set_at` | `effective_available`; `presence_changed` event |
| Python clock (one call site) | `now` | `on_shift = now ∈ window` — **derived, never stored** |
| `shared/events` writer | `Event` + typed detail | **write-only this slice — no read model (seam)** |
| `effective_available(profile,assignments,now)` | computed bool | **no consumer this slice — routing is the next slice (stated seam)** |

**Invariants visible in the flow:** roster is the single source of *when*, presence of *am-I-at-post*; `on_shift`/availability **derived, never stored** (anti-cache discipline); disable-not-delete (non-routable but audit-retained); every mutation emits exactly one append-only event even with no reader yet (the honest write-seam precedent); engineering assignment carries `section_id=null` — the model physically distinguishes the D12/D18 routing shapes *without building routing*.

## 10. Frontend

Reuse the merged auth/stay-binding/no-dispatch uniformity layer verbatim: TanStack Query (array keys, centralized invalidation, `api` client with `credentials:"include"` + 401→logout), `data-table-shell`/`page-header`/`status-badge`/`confirm`/`empty-state`/`error-state`/`combobox-field`/`date-range-field`, supervisor desktop-first / servicer mobile-first, the tightened monochrome tokens. **shadcn add-then-edit always; never re-`add` an edited component; never hand-author a primitive.**

- **Install (the only new shadcn this slice):** `toggle-group` (pulls `toggle`) — the servicer presence segmented control. Everything else is reuse or composition from installed primitives.
- **Compose new** (`components/common/`, edited tight): `staff-profile-form-dialog` (clone of `issue-code-form-dialog`), `skills-field` (Input+Badge chip set; local state → PUT replace-set), `roster-window-form-dialog` (wraps `date-range-field`), `assignment-editor` (combobox + 2 selects, inside the Sheet), `presence-control` (wraps `toggle-group`; disabled + reassuring caption off-shift), `shift-card`, `staff-presence-cell` (the at-a-glance monochrome glyph).
- **Hooks** (exact `use-issue-codes.ts` shape): `use-staff` (`['staff']`; create/patch profile, put skills), `use-rosters` (`['rosters']`, `['rosters',id,'assignments']`), `use-servicer-home` (`['servicer','home']`, polled per AD7), `use-presence`.
- **Pages:**
  - **Supervisor `/supervisor/staff`** — cloned from `issue-codes.tsx`: columns Name · Class (or "Not profiled" → primary action **Create profile**) · Skills (chips) · **Presence+Availability** as one composed monochrome glyph (`● Working · On shift` / `○ Off · Off shift`, weight/fill-differentiated, never a colour alarm) · Status · `⋯` (Create profile / Edit / Edit skills / Disable·Enable via `Confirm`). Reflows to cards `<md`.
  - **Supervisor `/supervisor/rosters`** — `data-table-shell` window list; row click → **side `Sheet`** with that window's assignment editor (inline add/edit; `combobox-field` servicer + section `Select` + role `Select`). The D12/D18 rule **taught in-UI** (the issue-codes "lock is taught" precedent): engineering selection auto-disables Section with a tooltip "Engineering is skill-matched, not section-pooled (D18)"; owner/backup makes Section required with an inline helper. Window form uses `date-range-field`.
  - **Servicer `/servicer` (home)** — replaces the stale stub. One calm mobile-first screen: identity (name + quiet class `role-badge` + skill chips), the **shift card** (Section · role · window + one derived live line: "On shift · ends in 3h 12m" / "Off shift · next 08:00" / "No upcoming shift"), the **presence control** (`toggle-group`; off-shift → disabled with the reassuring caption "Available when your shift starts" — the lock taught as care), and one secondary line teaching consequence ("On break and off pause new task routing"). Nothing else — the restraint is the design.
  - **Nav:** add "Staff" + "Rosters" under supervisor Setup; rebuild `servicer/nav.tsx` to the single real Home entry.
- **Cleanup:** replace the speculative `servicer/index.tsx` + `use-servicer.ts` (in-scope — this slice owns the servicer portal into existence). A separate **isolated drift-only commit** (no behaviour change) tightens any `rounded-xl`→`rounded-lg` / hand-rolled-state drift on older supervisor pages so the new pages don't sit next to inconsistent siblings (the no-dispatch isolated-style-commit precedent).

## 11. Test bench

**Guarantee, stated honestly first:** "pass ⇒ no manual re-check" holds for every documented behaviour **and** the guarded classes below; it is **not** a guarantee against an unspecified requirement. Inside that scope, green = comfort — and the structural guards extend it to whole *classes* of regression (route/contract drift, response-shape drift, role-gap, append-only violation) so even a regression introduced by a *later* slice trips them without anyone adding a test.

**Isolation — unconditional savepoint-rollback (the rollback-on-failure protection).** The merged `tests/spine/conftest.py`: one connection + one outer transaction per test; the `db_session` override hands the same session to the app so the app's edge `commit` lands in a `begin_nested()` SAVEPOINT (restarted via `after_transaction_end`). **Teardown rolls back the outer transaction unconditionally — pass, fail, or exception**: nothing the test or the app-inside-it wrote ever persists. A **leak sentinel** asserts the staffing (+ inherited spine/binding) tables at baseline between every test; the FK-ordered delete is a fallback *that must never fire* — if it does, it fails loudly.

**Time control — `freezegun`, made honest.** Business time (`presence_set_at`, the on-shift reference) flows through **one Python call site** that `freezegun` freezes; audit `created_at`/`updated_at` stay DB `func.now()` (tests never assert time-logic on them). `availability.py` is pure and takes `now` as a parameter — its exhaustive test needs no freezing at all; `freezegun` only pins the service/API entry for boundary cases.

**Layered:**
- *Migration* — `0004.down_revision==0003`; up/down round-trip; every CHECK/FK rejects; the three physical invariants tested **negative AND positive** (2nd profile rejected; dup skill rejected; 2nd active owner rejected **while** a disabled owner and the same person owning elsewhere are allowed).
- *Domain `availability.py`* — the **exhaustive truth-table**: `{off-shift,on-shift} × {working,on_break,off} × {set_at: in-window|pre-window|null} × {profile active|disabled}` + every boundary (`now == shift_start`, `now == shift_end`, `presence_set_at == window edge`). Total + deterministic ⇒ this single test proves the slice's core logic.
- *DAL* — add-only/no-flush; **self-scoped servicer DAL returns only the caller's own rows** (cross-account isolation, security-adjacent must-pass); `replace_skills` is the only deleting method (asserted).
- *Services* — every guard branch: the D12/D18 `422` split, off-shift presence `409`, create-profile-twice `409`, non-servicer `422`, disable-not-delete; exactly one append-only event+detail per mutation.
- *API* — full ASGI stack (`httpx.AsyncClient(ASGITransport)`), real per-role cookie chains, **every endpoint × every documented status** (happy + 401/403/404/409/422/405).

**Structural guards (the whole-classes-of-change net).** Inherited free: the auth-coverage meta-test auto-sweeps the new supervisor + servicer routes (an ungated route fails automatically). Added/asserted: **(1)** the **route/contract snapshot** — OpenAPI route+schema table serialized to a committed snapshot; any drift (renamed field, changed status, added/removed route) ⇒ red; regenerating it is the conscious "I meant to change the contract" step (§4). **(2)** response parse-back through `extra="forbid"` (account internals never leak through the `StaffOut` join). **(3)** role×endpoint matrix (every endpoint as every role incl. unauth; exact allow/deny). **(4)** append-only guard (one event+detail per mutation; no event update/delete path). **(5)** no-`DELETE`→`405` sweep over every staffing route. **(6)** named-exception guard (only `staff_skill` hard-replaces; nothing else hard-deletes). **(7)** the existing `--cov-fail-under=90` (unchanged — raising it moves the bar for merged code).

**E2E staffing sentinel:** supervisor profiles + rosters + assigns a servicer → servicer `/home` shows the derived shift → toggles working→on_break→working → `effective_available` flips correctly across on-shift/off-shift/disabled/yesterday's-toggle/exact-boundary → every mutation left exactly one append-only event → disable → non-routable → re-enable. Time pinned. Breaks loudly on any pipeline regression.

**CI:** Postgres required (the physical invariants can't be tested on SQLite); full suite incl. coverage gate + savepoint isolation + leak sentinel; red blocks merge.

## 12. Verification bar ("done" means)

Migration `0004` applies on no-dispatch's merged state and round-trips; the supervisor can profile a servicer (class + skills), create a roster window, and assign owner/backup/member with the D12/D18 rules enforced (DB CHECK + service `422` + the partial-unique `409`); the servicer portal renders the real home with the correctly-derived current/next shift; presence toggles only on-shift (server `409` off-shift) and is shift-scoped (yesterday's toggle never bleeds); `effective_available` is correct across the full exhaustive table including every boundary; disable-not-delete holds and no `DELETE` exists (`405`); every mutation left exactly one append-only `event` + detail; the contract snapshot matches (or was consciously regenerated); the full extended bench (layered + inherited + added structural guards + the e2e sentinel) is green under unconditional savepoint isolation; zero residue on a failing run.

## 13. Open / deferred (named, not silent)

- **Routing / dispatch / WorkOrder** — the immediate next slice; this slice builds exactly the data + the `availability` predicate it consumes.
- **Timers / stall / escalation spine** (D9/D10/D23) — later slices.
- **Generic event read model / awareness / analytics** — the evolution seam born here; read side deferred (as every prior slice deferred it).
- **Roster validity floor / overlap rejection** — D31 trusts valid config; accepted v1 limitation, revisit if pilot shows misconfiguration is common.
- **Shift-change handover** (D40) — manual, out-of-system, by decision.
- **Servicer self-service of class/skills** — supervisor-owned (D13); not a servicer capability.
- **The presence optimistic-default cost** — a rostered-but-absent servicer who forgot to toggle Off is routable until a later-slice stall surfaces it (D39-literal accepted cost, §4).
- **Multi-property** `property_id` denormalization (AD9) — additive when query patterns demand it.
- **Supervisor tightening micro-sweep** — drift-only, its own isolated commit; broader visual-system convergence is not this slice's job.
