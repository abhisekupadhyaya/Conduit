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

**In:** `Property` (single seeded row, AD9), `Section`, `Room`
(`section_id` FK), `Stay` (binds guest `Account` → `Room`, date range,
status); the generic append-only **`event`** base table + per-event-type
**detail tables** (relational, FK'd, no jsonb), write-only this slice; the
**second** Alembic migration (stacked on auth's first); the **ambient
resolution seam** (guest session resolves `{stay, room, section}`,
re-resolved every request so relocation needs no re-login);
supervisor-triggered `relocate_stay` + `checkout`; supervisor **Sections**
and **Provisioning / Check-in** pages on the auth slice's uniformity layer;
a test bench extending auth's harness.

**Out (by decision, not omission):**

- `staff_profile` / roster / skills / availability — the *routing* slice
  (next; D12/D18/D39).
- All SPINE work-unit entities (Request, ChildSubRequest, WorkOrder, Timer,
  Escalation, Glitch, …) — segments 2–3.
- The **glitch-driven** relocation trigger (engineer raises → decision queue
  → execute) — segment 3+. Only the supervisor-triggered re-bind is in.
- The generic event **read model** / awareness stream / activity UI —
  deferred until `event` has many writers and real content (first spine
  slice). The write seam is born here; the read side is not.
- `reservation_facts` — **removed from this slice entirely.** It was a held
  bag for D24's later late-checkout/billing mutations; no-jsonb + the fields
  are unknown until the slice that consumes them ⇒ it returns as a properly
  typed table in the D24 / no-dispatch slice. `Stay` here = guest + room +
  dates + status only.
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
| Entities | `Property` (1 seeded row), `Section` (CONFIG), `Room` (`section_id` FK), `Stay` (mutable `room_id`), generic `event` base + per-type detail tables (`event_stay_created`, `event_stay_ended`, `event_guest_relocated`) |
| No jsonb | Everything relational; every column a real FK or scalar. No jsonb anywhere. Event payload = typed columns on per-type detail tables, not a blob |
| Room→Section | `section_id` FK **field on Room** (entities.md Q2 answered: field, not a mapping entity); shift-recut **history not needed** — see "Section is derived" below |
| Section is derived | Section is **never stored on `Stay`** — always resolved `Stay → Room → Section`. This is *why* both relocation and a room→section re-cut propagate to ambient with **zero `Stay` writes**. Named principle, non-negotiable |
| Active stay | **Invariant: at most one `active` stay per guest.** Enforced by a Postgres **partial unique index** `(guest_account_id) WHERE status='active'` (race-proof, bad state physically impossible) **plus** a service guard for a clean domain `409` message. Room double-booking is *not* guarded (trust posture, D31/D27) |
| Property FKs | **Single-root: `property_id` on `Section` only.** Room→Section→Property, Stay→Room→Section→Property transitively. No single-value columns scattered; multi-property denormalizes deliberately later (additive migration, not a rewrite — satisfies AD9) |
| Dates | `check_in` / `check_out` = **`timestamptz`** (flow 04 is time-of-day-sensitive — late checkout till 2pm), even though unread this slice; avoids a later type migration |
| Ambient seam | `/auth/me` is **extended**, not a new route — guest role resolves the active stay → `{stay_id, room_id, room_label, section_id, section_label}`; `null` for non-guest / no active stay. Re-resolved **every request** (consistent with auth's status re-check) — this is *why* relocation needs no re-login |
| Transitions | Relocate and checkout are **dedicated action endpoints**, not generic PATCH — guarded state transitions that emit events (D20); benign field edits (`check_in/out`) use PATCH |
| Relocation trigger | **Supervisor action only.** The internal `relocate_stay` service is the exact seam the future glitch spine re-enters — kept clean, but no spine seam over-built now |
| Event seam | Generic append-only `event` base preserves entities.md's universal-log evolution seam (new type = new detail table + extended CHECK — additive, never migrates existing rows). Append-only enforced by no-app-write-path + asserted invariant (no DB trigger — ceremony at this volume) |
| Layering | `api → services → dal → models`; services raise domain errors (404/409/422), never `HTTPException`; services `flush`, commit at the request edge; ORM up, schema mapping at the API layer only |
| Portal ownership | Three **self-contained portals** (`guest`/`servicer`/`supervisor`), each with its own `dal`/`services`/`api`; **no cross-import among the three**. `public/` (auth, health) is the pre-portal front door, not a portal. A portal reaches the DB *only* through `shared/models` via its **own** DAL — the shared contract is the **model, not the DAL** |
| Binding read duplication | Supervisor owns binding CRUD + event writes (`supervisor/dal/`); the ambient resolver in `public/` has its **own** read (`public/dal/bindings.py`) over the *same shared models*. The ~one-function `Stay` read overlap is **intentional and cheap** — the price of portal self-containment; consistency is guaranteed by the shared model, not a shared DAL |
| Event scope | Events emitted on the **three stay transitions only** (`stay_created`/`stay_ended`/`guest_relocated`); benign date edits and section/room config changes emit **nothing** (not journey-meaningful transitions) |
| Deletes | **No `DELETE`** anywhere (D29 / lean). `DELETE → 405`, asserted as an invariant (mirrors auth) |

### Module ownership & layout

```
shared/models/        Property, Section, Room, Stay, Event(+3 detail)   ← DB contract
supervisor/dal/       sections.py rooms.py stays.py events.py           ← CRUD + event writes
supervisor/services/  sections.py rooms.py stays.py                     ← business logic, domain errors
supervisor/api/       setup.py (sections/rooms) + stays.py              ← thin: gate + map + 1 service call
public/dal/           bindings.py: get_active_binding_for_guest()       ← the one ambient read
public/services/auth.py  resolve_ambient()  (EXTEND — §6 seam)          ← auth-owned coordination point
```

- **`supervisor/dal/`** (imports `shared/models` only) — `sections.py`
  (`get` · `get_by_label` · `list_with_room_counts` · `insert` · `update`);
  `rooms.py` (`get` · `get_by_label` · `list` · `insert` · `update`);
  `stays.py` (`get` · `get_active_stay_for_guest` · `list` · `insert` ·
  `update_fields` · `set_room` · `set_status`); `events.py` (`insert_event`
  · `insert_stay_created` · `insert_stay_ended` · `insert_guest_relocated`
  — primitives only; the "which detail" branch is a service rule, not DAL).
- **`public/dal/bindings.py`** (imports `shared/models` only) —
  `get_active_binding_for_guest(db, guest_account_id) -> (Stay, Room,
  Section) | None`: the single joined read, read-only (public never writes
  binding data).
- **`supervisor/services/`** — `sections.py` (`list`, `create` [dup→409],
  `rename` [missing→404, dup→409]); `rooms.py` (`list`, `create`
  [section missing→422, dup→409], `update` [room missing→404, new section
  missing→422, dup→409]); `stays.py` (`list`; `create_stay`
  [guest not guest/active→422, room missing→422, existing active stay→409,
  then `event`+`stay_created`]; `update_stay` [missing→404, benign fields,
  **no event**]; `relocate_stay` [missing→404, not active→409, room
  missing→422, same room→409, then `event`+`guest_relocated`] — *the seam
  the future glitch spine re-enters*; `checkout_stay` [missing→404, not
  active→409, then `event`+`stay_ended`]).
- **`public/services/auth.py`** (EXTEND, auth-owned) — `resolve_ambient(db,
  account)`: `role != guest` → `None`; else `get_active_binding_for_guest`
  mapped to ambient fields or `None`. Owns the rule "only guests have
  ambient; no active stay ⇒ null." §6 cross-worktree coordination point.
- **Seed** (`python -m conduit.seed`, extended) — `ensure_property(db)`:
  idempotency is a rule (service/seed level); DAL stays plain
  (`get_singleton_property` / `insert_property`).

> Recorded as a one-line note in `code-structure.md` (mirroring how the
> auth slice recorded its DAL-ownership note): *portals are self-contained;
> the ambient binding read is duplicated in `public/dal/` by design.*

## 5. Data model

`conduit/shared/models/`, registered in `shared/models/__init__.py` so the
**second** Alembic autogenerate sees them, stacked on auth's first migration.
`uuid` pks and `timestamptz` defaults consistent with auth's `account`.
`text + CHECK` over PG enums (permissive structure, mechanism in code —
datamodels principle 5). **No jsonb anywhere.**

### Property `IDENTITY`
Single seeded row (like the bootstrap supervisor). Roots the hierarchy so
multi-property is later config, not a rewrite (AD9). No endpoints.

| Column | Type | Notes |
|---|---|---|
| `id` | `uuid` pk | |
| `name` | `text`, not null | |
| `created_at` / `updated_at` | `timestamptz` | |

### Section `CONFIG`
| Column | Type | Notes |
|---|---|---|
| `id` | `uuid` pk | join target for `room.section_id`, future `roster` |
| `property_id` | `uuid` fk → property | the single property-scoping FK (single-root) |
| `label` | `text`, not null | unique on `lower(label)` within property |
| `created_at` / `updated_at` | `timestamptz` | |

### Room `IDENTITY` / bridges to `Section`
| Column | Type | Notes |
|---|---|---|
| `id` | `uuid` pk | join target for `stay.room_id` |
| `section_id` | `uuid` fk → section, not null | exactly one section at a time (D12); **reassignable** |
| `label` | `text`, not null | unique on `lower(label)` within the room's property (e.g. "304") |
| `created_at` / `updated_at` | `timestamptz` | |

### Stay `IDENTITY`
| Column | Type | Notes |
|---|---|---|
| `id` | `uuid` pk | future `event` detail FK target |
| `guest_account_id` | `uuid` fk → `account.id` | role must be `guest` (service-checked) |
| `room_id` | `uuid` fk → room | **mutable** — relocation re-binds it |
| `check_in` / `check_out` | `timestamptz` | benign-editable; unread this slice |
| `status` | `text` + CHECK, default `active` | `active \| ended` (D29 spirit: end, never delete) |
| `created_at` / `updated_at` | `timestamptz` | |

- **Partial unique index:** `UNIQUE (guest_account_id) WHERE status =
  'active'` — at most one active stay per guest, physically.
- **Active stay** used by the resolver = `status='active'`. Date-range
  filtering (`now()` within `[check_in, check_out]`) is a later refinement
  (§12); the partial unique index makes "the active stay" singular today.
- **No `reservation_facts`** — out of this slice (§2).

### Generic event log — base + per-type detail (append-only, write-only)

**`event`** — the subject-agnostic universal timeline (entities.md's
evolution seam):

| Column | Type | Notes |
|---|---|---|
| `id` | `uuid` pk | |
| `type` | `text` + CHECK | `stay_created \| stay_ended \| guest_relocated` — extended additively per new type |
| `actor_account_id` | `uuid` fk → account, nullable | the supervisor who acted; null = system |
| `at` | `timestamptz`, default `now()` | the timeline order |

One **detail table per type**, 1:1 with its `event` row (`event_id` pk *and*
fk → `event`), carrying that type's typed FKs:

| `event_stay_created` | | | `event_stay_ended` | | | `event_guest_relocated` | |
|---|---|---|---|---|---|---|---|
| `event_id` | pk fk→event | | `event_id` | pk fk→event | | `event_id` | pk fk→event |
| `stay_id` | fk→stay | | `stay_id` | fk→stay | | `stay_id` | fk→stay |
| | | | | | | `from_room_id` | fk→room |
| | | | | | | `to_room_id` | fk→room |

A new event type later = a new detail table + one more `CHECK` value —
additive, never a data migration (the seam entities.md wants). Read models
(awareness stream, analytics) later query `event` for the timeline and join
the detail table for specifics. Append-only: no app update/delete path,
asserted.

> **Honest note (flagged, §12):** `stay_created`/`stay_ended` detail tables
> are thin and partly redundant with the `Stay` row's `status` +
> timestamps; only `guest_relocated` captures history otherwise lost
> (`Stay.room_id` is mutated in place). They are kept so the "*every*
> transition emits an event" uniformity holds — that uniformity is what
> makes the future awareness stream a clean read model. A later
> simplification may collapse the redundant ones; not now.

## 6. The ambient resolution seam (the heart)

Extend the auth `Actor` / `GET /api/auth/me` resolution. For `role=guest`:
resolve the single `active` `Stay` → attach
`{stay_id, room_id, room_label, section_id, section_label}` (section resolved
`Stay → Room → Section`, never stored on `Stay`). For non-guests, or a guest
with no active stay → these fields are `null` (D29 derived constraint: an
account with no active stay has nothing to action).

**Re-resolved every request**, consistent with the auth slice's "account
`status` re-checked every request, never trusted from the token." This is the
mechanism that makes relocation take effect with **no re-login, no re-setup**
(D20) — for free, by construction. It is also why a room→section re-cut moves
a sitting guest's ambient section with no `Stay` write.

⚠️ **Cross-worktree coordination point.** This is the *only* place this slice
reaches into auth-owned code (`public/services/auth.py` and the `AuthUser` /
`/auth/me` response schema). The auth slice's **contract-snapshot guard** will
flag the drift — that is correct and intended; it is resolved deliberately at
auth-merge time, not raced. The plan must sequence this change onto auth's
merged `/auth/me` and update the committed contract snapshot in the same
change.

## 7. Relocation mechanism

One guarded supervisor service `relocate_stay(stay_id, new_room_id, actor)`:

- Guards: stay must be `active` (`409`); `new_room` must exist (`422`);
  `new_room_id ≠ current room_id` (`409`, no-op rejected).
- Atomically, one transaction: update `Stay.room_id`; insert one `event`
  row (`type='guest_relocated'`, `actor_account_id`) + its
  `event_guest_relocated` detail (`from_room_id`, `to_room_id`).
- Section is **derived**, not stored — it follows the new room with no extra
  write.

Supervisor-triggered only in this slice. The service signature is the exact
seam the future glitch spine re-enters (it will call `relocate_stay`), but no
spine wiring is built now.

`checkout_stay(stay_id, actor)`: stay must be `active` (`409`); set
`status='ended'`; insert `event` + `event_stay_ended`. (Releases the
active-stay invariant so a returning guest can be re-checked-in — D29
persistent accounts.)

`create_stay(...)` likewise inserts `event` + `event_stay_created` in the
same transaction as the `Stay` insert.

## 8. API surface

Conventions inherited from the auth slice, unchanged: cookie session;
`/api/supervisor/*` admits only `supervisor` + `duty_manager` (guest/servicer
→ `403`, no cookie → `401`, server-side `require_roles` regardless of client);
domain errors `404/409/422`; response schemas `extra="forbid"`, internal
fields never serialized; services `flush`, commit at the request edge;
**no `DELETE`** (`405`, asserted).

### Cross-cutting — `GET /api/auth/me` extended (auth-owned file)
Adds, for `role=guest`: `stay_id, room_id, room_label, section_id,
section_label` (all `null` when no active stay; absent/`null` for
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
  duplicate label → `409`; unknown `section_id` → `422`
- `PATCH /api/supervisor/rooms/{id}` `{label?, section_id?}` → `200`
  (section reassign is real — D12 structure is supervisor-configured);
  unknown id → `404`; bad `section_id` → `422`; duplicate label → `409`
- No delete

### Supervisor — Stays (IDENTITY)
- `GET /api/supervisor/stays?status=&guest_id=` → `200 StayOut[]`
- `POST /api/supervisor/stays`
  `{guest_account_id, room_id, check_in, check_out}` → `201 StayOut`
  (check-in). Guards: guest exists & `role=guest` & `status=active`
  (`422`); room exists (`422`); **guest has no existing `active` stay**
  (service `409`; the partial unique index is the physical backstop).
- `PATCH /api/supervisor/stays/{id}` `{check_in?, check_out?}` → `200` —
  benign field edits only; **no `room_id`, no `status`** here on purpose;
  unknown id → `404`.
- `POST /api/supervisor/stays/{id}/relocate` `{new_room_id}` →
  `200 StayOut`. Guards per §7; unknown stay → `404`, unknown room → `422`.
- `POST /api/supervisor/stays/{id}/checkout` → `200 StayOut`; stay not
  `active` → `409`; unknown id → `404`.

### No API
`Property` — seeded single row, no endpoints. `event` + detail tables —
write-only this slice, no read route until they earn a read model.

**Shapes:** `SectionOut{id,label,room_count,created_at}`,
`RoomOut{id,label,section_id,section_label,created_at}`,
`StayOut{id,guest_account_id,guest_display_name,room_id,room_label,
section_id,section_label,check_in,check_out,status,created_at}`. The guest's
ambient fields on `/auth/me` per §6.

## 9. Frontend — hooks & pages

Reuse the auth slice's conventions and uniformity layer: TanStack Query
modules in `shell/<portal>/hooks/`, `lib/api-client.ts` with
`credentials:"include"` + centralized 401→logout, array query keys,
mutations invalidate by key prefix.

**Guest portal gets NO hook.** The guest's `{room, section, stay}` arrives
on the extended `/auth/me`, consumed by `auth-provider` **context** — the
session is one source of truth (context), never the query cache. The guest
shell reads ambient from `useAuth()`. *Honest consequence (D42/AD7 posture,
stated not hidden):* a relocated guest sees the new room on their **next
`/auth/me`** (`refreshUser()`, app refocus, or reload), not live — no guest
polling this slice; live reflection is a later spine/polling concern.

All hooks are **supervisor-portal only**, in `shell/supervisor/hooks/`
(mirroring auth's `use-accounts.ts` shape):

- `use-sections.ts` — `useSections()` → `['sections']`;
  `useCreateSection()`; `useRenameSection()`.
- `use-rooms.ts` — `useRooms(sectionId?)` → `['rooms', {sectionId}]`;
  `useCreateRoom()`; `useUpdateRoom()` (label and/or section reassign).
- `use-stays.ts` — `useStays(status?, guestId?)` →
  `['stays', {status, guestId}]`; `useCreateStay()` (check-in);
  `useRelocateStay()`; `useCheckoutStay()`; `useUpdateStay()` (benign dates).

**Response shapes embed derived labels** (`RoomOut.section_label`,
`StayOut.room_label`/`section_label`) — simple components, no client-side
joins, consistent with auth's `AccountOut`. The cost is **invalidation
fan-out**, centralized in one `invalidateBindingQueries(qc, keys)` helper so
no mutation hand-rolls it:

| Mutation | Invalidates |
|---|---|
| create / rename section | `['sections']`, `['rooms']`, `['stays']` |
| create / update room (incl. section reassign) | `['rooms']`, `['sections']` (room_count), `['stays']` (derived `section_label`) |
| create stay / relocate / checkout / update dates | `['stays']` |

- **No optimistic mutations this slice** (auth used optimism for
  enable/disable). Relocate/checkout emit events + re-resolve ambient;
  create/rename touch derived labels — all **await + toast**.
- **Not polled** — config/identity, not operational: default `staleTime` +
  refetch-on-focus, **no `refetchInterval`** (matches auth's account-list
  call; deliberately contrasts AD7's polled decision queue).
- The **check-in dialog composes existing hooks** (same-portal reuse,
  allowed): auth's `useAccounts('guest')` + `useStays('active')`, computing
  "guests with no active stay" client-side for the picker.
- Same responsive / async / skeleton bar as the auth slice (supervisor
  desktop-first, `data-table-shell` reflows to cards `< md`, ~180ms skeleton
  delay, skeleton on first load only + keep-previous-data on filter change).

### Component plan (shadcn-add-then-edit, always)

**Principle:** every shadcn component is installed via
`npx shadcn@latest add <c>` then edited for monochrome/tightness — **never
hand-authored** (consistency with the registry baseline). Each install gets
the same edit pass: kill default radii/shadows, neutralize focus rings to
`ring`, strip chromatic states (monochrome; `destructive` stays).

- **Reuse — already in `components/ui/` (13):** button, input, label,
  field, separator, avatar, dropdown-menu (the `⋯` row menu — same pattern
  auth uses for accounts), sidebar, sheet, skeleton, tooltip, breadcrumb,
  collapsible.
- **Provided by the auth slice — consume, do NOT re-add** (re-adding
  clobbers the auth agent's edits — a hard coordination rule): card, form,
  table, dialog, alert-dialog, sonner, badge, select, alert, tabs + the
  shared primitives `page-header`, `empty-state`, `error-state`,
  `status-badge`, `role-badge`, `confirm`, `data-table-shell`.
- **This slice installs (net-new, nothing else needs them):**
  `popover`, `calendar`, `command`, `accordion`.
- **Composed patterns** (registry has no component — built once in
  `components/common/`, edited tight, reused by both dialogs):
  `combobox-field.tsx` (`command`+`popover` — searchable guest/room
  pickers; chosen over plain Select because hotel guest/room lists don't
  scroll well), `date-range-field.tsx` (`calendar`+`popover`+`button` —
  check-in/out range).

### Pages

- **Sections** — `/supervisor/setup/sections`. `PageHeader`
  ("Sections" + `N sections · M rooms` + primary **New section**).
  **`accordion`**: each section row = label · room count · `⋯` (Rename);
  expand → a dense **wrapped chip grid of rooms** + inline **Add room**;
  a room chip → `⋯` (Rename / Reassign section via `combobox-field`).
  Master/detail in one dense view, no drill-down. `EmptyState` (no
  sections), `ErrorState` (retry), skeleton accordion on first load.
- **Provisioning / Check-in** — `/supervisor/provisioning`. `PageHeader`
  ("Provisioning" + `N active stays` + primary **Check in guest**).
  Toolbar: status segmented (Active / Ended / All) + client search.
  `data-table-shell`: guest (avatar+name) · room · section · `check-in →
  out` (compact) · **status as a quiet `•` dot + label, not a loud pill**
  · `⋯` (dropdown-menu: **Move guest…**, **Check out**). Reflows to cards
  `< md`.
  - **Move guest** `Dialog` — deliberate, not a generic edit (D20 is the
    product's one stateful mutation): shows `current room · section ──▶
    [room combobox]`, live-previews the resulting section, and carries the
    honest §6 line in-UI ("re-binds immediately; the guest sees it on next
    refresh — no re-login"). **Await + toast**, not optimistic.
  - **Check out** → the auth `confirm` (AlertDialog) primitive.
  - **Check in guest** `Dialog` — single-column, `max-w` capped: guest
    `combobox-field` (filtered to no-active-stay), room `combobox-field`,
    `date-range-field`; auth's async/skeleton bar.
- **Nav (this slice's wiring):** add a **Sections** item under
  `Setup` (the existing `supervisorNav` "Sections & Rosters" entry →
  point its Sections half here; Rosters stays a next-slice stub);
  **Guest Provisioning** (existing nav entry, `/supervisor/provisioning`)
  → the Check-in page. Routes wired in `App.tsx` + `supervisorNav`.

### Design system & tightness — coordinate at the auth merge (NOT now)

The shell/primitive uniformity-and-tightness pass is **auth-slice-owned and
in-flight** (its scope includes retrofitting the placeholder shells onto
the primitives and the monochrome token cleanup incl. the stray dark
`--sidebar-primary` indigo at `index.css:112`). Two agents tightening the
same global tokens in parallel produces a merge mess and an incoherent
product. So this slice **does not edit `index.css`/primitives**; it records
the target so it is applied **once, coordinated, when auth's layer merges**:

- **Aesthetic:** an operations console (Linear / Vercel-dashboard /
  flight-ops) — calm, dense, precise. Color = meaning only (`destructive`;
  a single operational accent deferred to the awareness/decision surfaces).
- **Tighten geometry:** target `--radius ≈ 0.4rem` (current `0.625rem`
  with xl/2xl/3xl multipliers is pillowy for an ops tool); hairline
  borders; compact controls (`h-9`); denser table rhythm.
- **Hierarchy by weight, not size**; status by weight + a quiet dot, never
  loud pills.
- **Action:** owner of the merge applies these to the shared tokens once;
  this slice's pages are built to *look right under that target* and
  verified at the merge seam (pairs with the §6 / contract-snapshot
  coordination — same checkpoint).

## 10. Test bench

**Goal & honest boundary.** "Pass ⇒ no manual re-check" is only honest if a
regression *cannot* ship without turning the suite red. The bench is built so
tests are not just examples but **structural guards failing on whole classes
of change** (a new field, a renamed route, a dropped authz check, an untested
branch). The guarantee holds for every documented behaviour **and** these
guarded classes; it is **not** a guarantee against a requirement never
specified. Stated plainly so the comfort is real, not false.

Extends the auth slice's harness (throwaway `conduit_test` DB built via
`alembic upgrade head` — now including the second migration — leak sentinel,
the structural guards, coverage gate). Precondition data built through the
**real services** (`create_account` from auth, then `create_stay`), never raw
inserts.

**Layered (each layer catches what the one above can't):**
- **Migration** — 2nd migration `down_revision` = auth's; `upgrade`→
  `downgrade` round-trips clean; the **partial unique index physically
  rejects a 2nd active stay** (raw insert, not via service); every
  CHECK/FK actually rejects (`status`, `event.type`, bad FKs).
- **DAL** (`supervisor/dal/*` + `public/dal/bindings.py`) —
  case-insensitive label lookup; filters; FK integrity;
  `get_active_binding_for_guest` returns the correct trio / `None`;
  event-insert primitives.
- **Services** — **every branch of every guard** (`create_stay`,
  `relocate_stay`, `checkout_stay`, `update_stay` no-event, sections/rooms
  branches, `resolve_ambient` non-guest/no-active/active).
- **API** — full stack via `httpx.AsyncClient(ASGITransport)`, real
  cookie-auth chains: every endpoint's happy path **and every error
  status**.

**Structural guards (inherited from auth, extended here — the regression
net):**
1. **Contract snapshot** — committed `{path,methods,auth,status}` from the
   live OpenAPI schema; *any* drift fails until the snapshot is
   **intentionally** updated. **Owns asserting the extended `/auth/me`
   ambient shape** — if the auth merge ever drops/renames an ambient field,
   *this* slice's suite goes red at the seam (the deliberate §6
   coordination artifact).
2. **Response-schema parsing** — every response parsed into an
   `extra="forbid"` model → catches leaked *and* dropped fields on
   `SectionOut`/`RoomOut`/`StayOut` and the `/auth/me` ambient fields.
3. **Parametric role × endpoint matrix** — authz expectations *generated*
   over all `/supervisor/*` routes × all roles; a new route is
   **auto-covered** (guest/servicer→403, no-cookie→401,
   supervisor/duty_manager→allowed). An unguarded endpoint cannot ship.
4. **Auth-coverage meta-test** — every route not in the public allowlist
   returns 401 without a cookie.
5. **Coverage gate** — `--cov fail-under`, **branch coverage, scoped to the
   binding modules**: 100% on `dal`+`services`, high on `api`. An untested
   branch fails the suite.
6. **Leak sentinel** — between modules assert binding tables at seeded
   baseline (`Property=1`, sections/rooms/stays/events=0). A missed
   teardown fails **loudly**, never silently passes.

**End-to-end journey sentinel (the test you actually trust):** one scripted
test that *is* this slice's journey — seed supervisor → create section+room
→ create guest (auth service) → check-in → guest `GET /auth/me` shows
ambient → **relocate** → same guest's next `/auth/me` shows new
room+section (**no re-login**) → reassign the room's section → ambient
section follows (**no `Stay` write**) → checkout → `/auth/me` ambient
`null` → re-check-in allowed. Breaks loudly if any pipeline stage
regresses.

**Isolation / zero-residue (no residue even on failure).** Tests are
written **mechanism-agnostic** — a test must never depend on the isolation
strategy. The harness's isolation lives in the auth-owned `conftest.py`
(in-flight); the **target recorded here is transactional savepoint-rollback**
(`join_transaction_mode="create_savepoint"`, the `AsyncClient` sharing the
bound connection, rollback in the fixture finalizer — true rollback even on
a hard crash, faster, no FK-ordered delete to maintain). It is applied
**once, coordinated, at the auth merge** (same checkpoint as §6 / contract
snapshot) — not bolted on in parallel (two isolation strategies in one
conftest ⇒ flakiness). Until then auth's model-delete-in-`finally` + leak
sentinel already delivers zero-residue-on-failure; this slice's tests pass
under either.

**Named invariants (one test each):**
1. Ambient follows a relocation **atomically** — `relocate` then
   `GET /auth/me` (same cookie, **no re-login**) reflects the new room +
   derived section on the very next call.
2. At most one `active` stay per guest — second `POST /stays` → service
   `409`; **and** a direct second active insert is rejected by the partial
   unique index (the physical backstop is real, not just the service).
3. Cannot `relocate` or `checkout` a non-`active` stay → `409`.
4. Guest with no active stay → ambient fields `null` on `/auth/me`.
5. `relocate` to the current room → `409` (no-op rejected).
6. Every transition inserts exactly one `event` of the right `type` **and**
   its matching detail row; `event` + detail tables have no update/delete
   path (append-only).
7. `DELETE` on every new route → `405`.
8. Section is derived: reassigning a room's `section_id` changes the ambient
   `section_*` for a guest currently in that room, **with no `Stay` write**.
9. Contract snapshot updated to include the extended `/auth/me` and all new
   routes (the guard is green *because* the snapshot was intentionally
   updated, not bypassed).

**CI:** Postgres required; red suite (incl. coverage gate) blocks merge.

## 11. Verification bar ("done" means)

Second migration applies on top of auth's merged state and round-trips
(incl. the partial unique index); `Property` + sections + rooms
seedable/creatable; a supervisor checks a guest in; that guest logs in on the
shared page and `/auth/me` carries `{room, section, stay}`; the supervisor
relocates the guest and the **same logged-in guest's** next `/auth/me`
reflects the new room+section with **no re-login**; reassigning a room to
another section moves the in-room guest's ambient section with no `Stay`
write; checkout ends the stay and a returning check-in is allowed; every
transition left an append-only `event` + detail row; the full extended test
bench (layered + inherited structural guards + the 9 named invariants) is
green.

## 12. Open / deferred (named, not silent)

- **Generic event read model / awareness stream / activity UI** — first
  spine slice. Write seam born here; read side deferred.
- **Redundant `stay_created`/`stay_ended` detail tables** — kept for
  "every transition emits an event" uniformity; a later pass may collapse
  them once the read model exists. Conscious, not an oversight.
- **In-flight child-request handling on relocation** — segment 3 (no
  children exist yet; the re-bind mechanism is built, the consequence isn't).
- **Date-range-aware "active stay"** — resolver uses `status='active'` only;
  `now()`-within-`[check_in, check_out]` filtering is a later refinement.
- **Room→Section history** on shift re-cuts — not needed (section is derived,
  nothing stores a point-in-time copy to reconcile); revisit only if a query
  pattern ever demands it.
- **`reservation_facts`** — out of this slice; returns as a properly typed
  table in the D24 / no-dispatch slice that consumes it.
- **`property_id` on Room/Stay** — single-root for now; denormalize
  additively if/when multi-property query patterns demand it.
- **`staff_profile` / roster / skills / availability** — the routing slice,
  the immediate next segment after this one.
- **Global design-system tightness** (radius ≈ 0.4rem, density, accent
  policy) — captured in §9; applied once, coordinated, at the auth-layer
  merge (same checkpoint as the §6 / contract-snapshot seam). Deliberately
  *not* edited by this slice to avoid parallel token-fighting with the
  in-flight auth uniformity layer.
- **Test-isolation upgrade to savepoint-rollback** — target recorded in
  §10; applied once to the auth-owned `conftest.py` at the auth merge.
  Tests here are mechanism-agnostic so the decision needs no change to this
  slice. Same merge checkpoint as the design-system + §6 seams.
