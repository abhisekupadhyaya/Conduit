# Stay / Binding Slice — Design ("Check-in & Relocation")

| | |
|---|---|
| **Status** | Approved design (2026-05-16) |
| **Scope** | Journey segment after auth: supervisor checks a guest in → guest's session resolves ambient {room, section, stay}; mid-stay relocation re-binds it |
| **Source of truth** | Product decisions (D-series) — *what*; data-model docs — *shape*; this doc — *this slice* |
| **Depends on** | The auth slice (`feat/auth-slice`) merging — account model, first migration, cookie session, supervisor gating, conftest harness |

## 1. Why this slice

Slicing is by **journey segment**, not data-model layer — every slice must close a
real, demoable gap in a user journey.

Auth completes the *provisioned → login* beat. Every flow's precondition then
assumes ambient `{room, section, stay}` ("After login the session carries
{guest, stay, room, section}"). Auth delivers the account and the login half;
it leaves the `{stay, room, section}` half dangling — a guest can log in and
the app knows *who* they are but not *where*. This slice closes that segment:
the supervisor checks a guest in, and the guest's session resolves ambient
context.

It also front-loads the one event in the entire product that **mutates**
ambient context — relocation (D20/D29). Proving the binding is re-bindable now,
while it is inert IDENTITY data with no SPINE reading it, is far cheaper than
retrofitting mutability once triage/routing/lifecycle all depend on
`{room, section}`.

## 2. Scope

**In:** `Property` (single row, AD9), `Section`, `Room` (`section_id` FK),
`Stay` (binds guest `Account` → `Room`, date range, status,
reservation-facts bag); the **second** Alembic migration (stacked on auth's
first); the **ambient resolution seam** (guest session resolves
`{stay, room, section}`, re-resolved every request so relocation needs no
re-login); supervisor-triggered `relocate_stay` + `checkout`; a minimal
**append-only `event` table**, write-only, first-written by stay-create /
checkout / relocate; supervisor **Sections** and **Provisioning / Check-in**
pages on the auth slice's uniformity layer; a test bench extending auth's
harness.

**Out (by decision, not omission):**

- `staff_profile` / roster / skills / availability — the *routing* slice
  (next; D12/D18/D39).
- All SPINE entities (Request, ChildSubRequest, WorkOrder, Timer,
  Escalation, Glitch, …) — segments 2–3.
- The **glitch-driven** relocation trigger (engineer raises → decision queue
  → execute) — segment 3+. Only the supervisor-triggered re-bind is in.
- Event **read model** / awareness stream / activity UI — deferred until Event
  has many writers and real content (the first spine slice).
- Reservation-fact **mutation** logic (D24) — `Stay` only *holds* reservation
  facts here; mutating them is the no-dispatch / flag spine later.
- "What happens to in-flight child requests on relocation" — no children
  exist yet; **flagged, not solved** (segment 3).
- Multi-property scoping beyond a single `Property` row (AD9).

## 3. Dependency & sequencing

Hard dependency on `feat/auth-slice` merging. This slice's migration is the
**second** Alembic version, stacked on auth's first; its tests extend auth's
conftest harness; its supervisor pages reuse auth's uniformity layer; its one
cross-cutting change extends auth's `/auth/me`.

⇒ **Design + plan now (zero merge risk, docs only); execute after auth lands.**
The auth worktree is independently in flight and will be reviewed separately;
this slice is deliberately authored to *stack on* auth's merged state, not race
it.

## 4. Decision ledger

| Area | Locked decision |
|---|---|
| Entities | `Property` (1 row, seeded), `Section` (CONFIG), `Room` (`section_id` FK — exactly one section at a time, D12), `Stay` (mutable `room_id`), `Event` (append-only, write-only this slice) |
| Room→Section | A `section_id` FK **field on Room** (entities.md Q2 answered: field, not a mapping entity); shift-recut **history deferred** |
| Active stay | **Invariant: at most one `active` stay per guest account.** Makes the ambient resolver deterministic ("*the* active stay" is unambiguous). Room double-booking is *not* guarded (trust posture, D31/D27) |
| Ambient seam | `/auth/me` is **extended**, not a new route — guest role resolves the active stay → `{stay_id, room_id, room_label, section_id, section_label}`; `null` for non-guest / no active stay. Re-resolved **every request** (consistent with auth's status re-check) — this is *why* relocation needs no re-login |
| Transitions | Relocate and checkout are **dedicated action endpoints**, not generic PATCH — they are guarded state transitions that emit events (D20); benign field edits (`check_in/out`, `reservation_facts`) use PATCH |
| Relocation trigger | **Supervisor action only.** The internal `relocate_stay` service is the exact seam the future glitch spine re-enters — kept clean, but no spine seam over-built now |
| Event | Table born now (entities.md: every transition appends one; primary evolution seam — retrofitting later is the mistake to avoid). **No read model / UI** until it has many writers |
| Layering | `api → services → dal → models`; services raise domain errors (404/409/422), never `HTTPException`; services `flush`, commit at the request edge; ORM up, schema mapping at the API layer only |
| Deletes | **No `DELETE`** anywhere (D29 / lean): identity & config persist. `DELETE → 405`, asserted as an invariant (mirrors auth) |
| Property | Seeded single row (like the bootstrap supervisor) — **no endpoints** |

## 5. Data model

`conduit/shared/models/`, registered in `shared/models/__init__.py` so the
**second** Alembic autogenerate sees them, stacked on auth's first migration.
`text + CHECK` over PG enums; permissive structure, mechanism in code
(datamodels principle 5).

### Property `IDENTITY`
Single row in v1; everything property-scoped via FK so multi-property is later
config, not a rewrite (AD9). Seeded.

### Section `CONFIG`
| Column | Type | Notes |
|---|---|---|
| `id` | `uuid` pk | join target for `room.section_id`, future `roster` |
| `property_id` | `uuid` fk | AD9 |
| `label` | `text`, not null | unique on `lower(label)` within property |
| `created_at` / `updated_at` | `timestamptz` | |

### Room `IDENTITY` / bridges to `Section`
| Column | Type | Notes |
|---|---|---|
| `id` | `uuid` pk | join target for `stay.room_id` |
| `property_id` | `uuid` fk | |
| `label` | `text`, not null | unique on `lower(label)` within property (e.g. "304") |
| `section_id` | `uuid` fk, not null | exactly one section at a time (D12); reassignable |
| `created_at` / `updated_at` | `timestamptz` | |

### Stay `IDENTITY`
| Column | Type | Notes |
|---|---|---|
| `id` | `uuid` pk | future `event.subject`, future spine ambient |
| `guest_account_id` | `uuid` fk → `account.id` | role must be `guest` (service-checked) |
| `room_id` | `uuid` fk | **mutable** — relocation re-binds it |
| `check_in` / `check_out` | `date` (or `timestamptz`) | range; benign-editable |
| `status` | `text` + CHECK, default `active` | `active \| ended` (D29 spirit: end, never delete) |
| `reservation_facts` | `jsonb`, default `{}` | permissive bag — the things D24 mutations will later touch; *held*, not mutated here |
| `created_at` / `updated_at` | `timestamptz` | |

**Active-stay invariant:** at most one `status='active'` stay per
`guest_account_id`. Enforced in the service on create (partial unique index a
later hardening option — service guard is sufficient and explicit for v1).
"Active stay" used by the resolver = `status='active'` (date-range filtering
is a later refinement; flagged §9).

### Event `SPINE` — append-only, write-only this slice
| Column | Type | Notes |
|---|---|---|
| `id` | `uuid` pk | |
| `actor_account_id` | `uuid` fk, nullable | the supervisor who acted; null for system |
| `subject_type` | `text` | `stay` (only value this slice) |
| `subject_id` | `uuid` | the stay id |
| `type` | `text` | `stay_created \| stay_ended \| guest_relocated` |
| `payload` | `jsonb` | e.g. `{from_room_id, to_room_id}` for relocate |
| `at` | `timestamptz`, default `now()` | |

No update/delete path exists (append-only — asserted as an invariant). New
event types are additive; this is the product's primary evolution seam.

## 6. The ambient resolution seam (the heart)

Extend the auth `Actor` / `GET /api/auth/me` resolution. For `role=guest`:
resolve the single `active` `Stay` → attach
`{stay_id, room_id, room_label, section_id, section_label}` (section derived
via `room.section_id`, never stored on `Stay` — so it follows a relocation
automatically). For non-guests, or a guest with no active stay → these fields
are `null` (D29 derived constraint: an account with no active stay has nothing
to action).

**Re-resolved every request**, consistent with the auth slice's "account
`status` re-checked every request, never trusted from the token." This is the
mechanism that makes relocation take effect with **no re-login, no re-setup**
(D20) — for free, by construction.

⚠️ **Cross-worktree coordination point.** This is the *only* place this slice
reaches into auth-owned code (`public/services/auth.py` and the `AuthUser` /
`/auth/me` response schema). The auth slice's **contract-snapshot guard** will
flag the drift — that is correct and intended; it is resolved deliberately at
auth-merge time, not raced. The plan must sequence this change to land on
auth's merged `/auth/me`, and update the committed contract snapshot in the
same change.

## 7. Relocation mechanism

One guarded supervisor service `relocate_stay(stay_id, new_room_id, actor)`:

- Guards: stay must be `active` (`409`); `new_room` must exist in the same
  property (`422`); `new_room_id ≠ current room_id` (`409`, no-op rejected).
- Atomically: update `Stay.room_id`; append a `guest_relocated` event
  (`payload={from_room_id, to_room_id}`); same transaction.
- Section is **derived**, not stored — it follows the new room with no extra
  write.

Supervisor-triggered only in this slice. The service signature is the exact
seam the future glitch spine re-enters (it will call `relocate_stay`), but no
spine wiring is built now.

`checkout_stay(stay_id, actor)`: stay must be `active` (`409`); set
`status='ended'`; append `stay_ended`. (Releases the active-stay invariant so
a returning guest can be re-checked-in — D29 persistent accounts.)

## 8. API surface

Conventions inherited from the auth slice, unchanged: cookie session;
`/api/supervisor/*` admits only `supervisor` + `duty_manager` (guest/servicer
→ `403`, no cookie → `401`, server-side `require_roles` regardless of client);
domain errors `404/409/422`; response schemas `extra="forbid"`,
internal/`secret_hash` never serialized; services `flush`, commit at the
request edge; **no `DELETE`** (`405`, asserted).

### Cross-cutting — `GET /api/auth/me` extended (auth-owned file)
Adds, for `role=guest`: `stay_id, room_id, room_label, section_id,
section_label` (all `null` when no active stay; all `null`/absent for
non-guests). No new guest route. See §6 for the coordination/guard note.

### Supervisor — Sections (CONFIG)
- `GET /api/supervisor/sections` → `200 SectionOut[]` (incl. room count)
- `POST /api/supervisor/sections` `{label}` → `201 SectionOut`; duplicate
  label (case-insensitive, within property) → `409`
- `PATCH /api/supervisor/sections/{id}` `{label}` → `200`; unknown → `404`;
  duplicate → `409`
- No delete (reorg = reassign rooms)

### Supervisor — Rooms (IDENTITY)
- `GET /api/supervisor/rooms?section_id=` → `200 RoomOut[]`
- `POST /api/supervisor/rooms` `{label, section_id}` → `201 RoomOut`;
  duplicate label → `409`; unknown/!exist `section_id` → `422`
- `PATCH /api/supervisor/rooms/{id}` `{label?, section_id?}` → `200`
  (section reassign is real — D12 structure is supervisor-configured);
  unknown id → `404`; bad `section_id` → `422`; duplicate label → `409`
- No delete

### Supervisor — Stays (IDENTITY)
- `GET /api/supervisor/stays?status=&guest_id=` → `200 StayOut[]`
- `POST /api/supervisor/stays`
  `{guest_account_id, room_id, check_in, check_out}` → `201 StayOut`
  (check-in). Guards: guest exists & `role=guest` & `status=active`
  (else `422`); room exists same property (`422`); **guest has no existing
  `active` stay** (`409`).
- `PATCH /api/supervisor/stays/{id}`
  `{check_in?, check_out?, reservation_facts?}` → `200` — benign field edits
  only; **no `room_id`, no `status`** here on purpose; unknown id → `404`.
- `POST /api/supervisor/stays/{id}/relocate` `{new_room_id}` →
  `200 StayOut`. Guards per §7; unknown stay/room → `404`/`422`.
- `POST /api/supervisor/stays/{id}/checkout` → `200 StayOut`; stay not
  `active` → `409`; unknown id → `404`.

### No API
`Property` — seeded single row, no endpoints. `Event` — write-only this
slice, no read route until it earns a read model.

**Shapes:** `SectionOut{id,label,room_count,created_at}`,
`RoomOut{id,label,section_id,section_label,created_at}`,
`StayOut{id,guest_account_id,guest_display_name,room_id,room_label,
section_id,section_label,check_in,check_out,status,reservation_facts,
created_at}`. The guest's ambient fields on `/auth/me` per §6.

## 9. Frontend — hooks & pages

Reuse the auth slice's conventions and uniformity layer. All API access via
TanStack Query in `shell/supervisor/hooks/`; relocation/checkout are
mutations that invalidate `['stays']`.

- `shell/supervisor/hooks/use-sections.ts`, `use-rooms.ts`, `use-stays.ts` —
  query + mutation modules (mirroring auth's `use-accounts.ts` shape).
- The guest shell consumes the extended `/auth/me` via the existing
  `auth-provider` context — **no new guest data fetching** (ambient is part
  of the session, one source of truth).
- **Sections page** — `PageHeader` + `data-table-shell`: section label ·
  room count · `⋯` (Rename). "Add section" `Dialog`.
- **Provisioning / Check-in page** — stays `data-table-shell`: guest ·
  room · section · dates · status `Badge` · `⋯` (**Move guest** →
  relocate confirm `Dialog` with room picker; **Check out** → `confirm`).
  "Check in guest" `Dialog` (guest picker filtered to guests with no active
  stay, room picker, dates).
- Rooms managed inline within the Sections page (assign/reassign room →
  section), reusing the same primitives — no separate Rooms page in v1.
- Same responsive / async / skeleton bar as the auth slice (role
  desktop-first for supervisor, tables reflow to cards `< md`, optimistic
  only where safe — relocation/checkout are **await + toast**, not
  optimistic, since they emit events and re-resolve ambient).
- New routes wired in `App.tsx` + `supervisorNav`.

## 10. Test bench

Extends the auth slice's harness (throwaway `conduit_test` DB built via
`alembic upgrade head` — now including the second migration — model-delete
teardown, leak sentinel, the 5 structural guards, coverage gate). Precondition
data built through the **real services** (`create_account` from auth, then
`create_stay`), never raw inserts.

**Layered:** second migration round-trips on top of auth's first; DAL
(case-insensitive label lookup, FK integrity, filters); services (every
branch incl. all guards); API (full stack, role × endpoint matrix —
auto-covers the new supervisor routes via the inherited parametric guard).

**Named invariants (one test each):**
1. Ambient follows a relocation **atomically** — `relocate` then
   `GET /auth/me` (same cookie, **no re-login**) reflects the new room +
   derived section on the very next call.
2. At most one `active` stay per guest — second `POST /stays` for a guest
   with an active stay → `409`.
3. Cannot `relocate` or `checkout` a non-`active` stay → `409`.
4. Guest with no active stay → ambient fields `null` on `/auth/me`.
5. `relocate` to the current room → `409` (no-op rejected).
6. Every transition appends exactly one `event` of the right `type`;
   `event` has no update/delete path (append-only).
7. `DELETE` on every new route → `405`.
8. Section is derived: reassigning a room's `section_id` changes the
   ambient `section_*` for a guest currently in that room, with no stay write.
9. Contract snapshot updated to include the extended `/auth/me` and all new
   routes (the guard is green *because* the snapshot was intentionally
   updated, not bypassed).

**CI:** Postgres required; red suite (incl. coverage gate) blocks merge.

## 11. Verification bar ("done" means)

Second migration applies on top of auth's from auth's merged state and
round-trips; `Property` + sections + rooms seedable/creatable; a supervisor
checks a guest in; that guest logs in on the shared page and `/auth/me`
carries `{room, section, stay}`; the supervisor relocates the guest and the
**same logged-in guest's** next `/auth/me` reflects the new room+section with
**no re-login**; checkout ends the stay and a returning check-in is allowed;
reassigning a room to another section moves the in-room guest's ambient
section with no stay write; every transition left an append-only `event`;
the full extended test bench (layered + inherited structural guards + the 9
named invariants) is green.

## 12. Open / deferred (named, not silent)

- **Event read model / awareness stream / activity UI** — first spine slice.
- **In-flight child-request handling on relocation** — segment 3 (no
  children exist yet; the re-bind mechanism is built, the consequence isn't).
- **Date-range-aware "active stay"** — resolver uses `status='active'` only;
  now-within-`[check_in,check_out]` filtering is a later refinement.
- **Room→Section history** on shift re-cuts (entities.md Q2) — field now,
  history if a query pattern ever needs it.
- **Reservation-fact mutation** (D24) — held here, mutated in the
  no-dispatch / flag spine.
- **`staff_profile` / roster / skills / availability** — the routing slice,
  the immediate next segment after this one.
- Partial unique index hardening the active-stay invariant (service guard is
  the v1 mechanism).
