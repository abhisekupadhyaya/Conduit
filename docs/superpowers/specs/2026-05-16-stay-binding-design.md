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
| Ambient seam | `/auth/me` is **extended**, not a new route. The response model is `AuthUser` in `conduit/public/schemas/auth.py` (`ConfigDict(from_attributes=True)`, no `extra=forbid`) — add **five optional** ambient fields defaulting `None`. The `/me` handler builds `AuthUser` from the account **plus** `resolve_ambient`. `resolve_ambient(s, actor)` takes the `Actor` (frozen `Actor(id:str, role:str)` from `current_actor`), guest-only, else `None`. `login` also returns `AuthUser`; it simply carries `None` ambient (the SPA bootstraps via `/me`, which is polled) — acceptable, no login change. Re-resolved **every request** — *why* relocation needs no re-login |
| Transitions | Relocate and checkout are **dedicated action endpoints**, not generic PATCH — guarded state transitions that emit events (D20); benign field edits (`check_in/out`) use PATCH |
| Relocation trigger | **Supervisor action only.** The internal `relocate_stay` service is the exact seam the future glitch spine re-enters — kept clean, but no spine seam over-built now |
| Event seam | Generic append-only `event` base preserves entities.md's universal-log evolution seam (new type = new detail table + extended CHECK — additive, never migrates existing rows). Append-only enforced by no-app-write-path + asserted invariant (no DB trigger — ceremony at this volume) |
| Layering | `api → services → dal → shared/models`; **fully async** (`AsyncSession`, `await s.execute/get`, `async def` all the way down — matches the merged auth code). Services raise domain errors, never `HTTPException`; **DAL adds, does not flush** (auth precedent: `insert_account` is add-only); **services `await s.flush()`** when an id is needed; **the API handler `await s.commit()`s** after a mutating service call (read endpoints never commit) — exactly the merged `create_account` handler pattern. ORM up, schema mapping at the API layer only |
| Errors / 422 | Domain errors map via `core/exceptions.py` (`ConduitError`=400 base, `NotFoundError`=404, `AuthError`=401, `ForbiddenError`=403, `ConflictError`=409). There is **no 422 class in the merged code** — this slice **adds `ValidationError(ConduitError); status_code=422`** (additive, exactly how auth added `ConflictError`). Invalid-guest / unknown-room → `ValidationError` (422); a raw `ValueError` would 500 (handler only catches `ConduitError`) |
| Portal ownership | Three **self-contained portals** (`guest`/`servicer`/`supervisor`), each with its own `dal`/`services`/`api`; **no cross-import among the three**. `public/` (auth, health) is the pre-portal front door, not a portal. A portal reaches the DB *only* through `shared/models` via its **own** DAL — the shared contract is the **model, not the DAL** |
| Binding read duplication | Supervisor owns binding CRUD + event writes (`supervisor/dal/`); the ambient resolver in `public/` has its **own** read (`public/dal/bindings.py`) over the *same shared models*. The ~one-function `Stay` read overlap is **intentional and cheap** — the price of portal self-containment; consistency is guaranteed by the shared model, not a shared DAL |
| Event scope | Events emitted on the **three stay transitions only** (`stay_created`/`stay_ended`/`guest_relocated`); benign date edits and section/room config changes emit **nothing** (not journey-meaningful transitions) |
| Deletes | **No `DELETE`** anywhere (D29 / lean). `DELETE → 405`, asserted as an invariant (mirrors auth) |

### Module ownership & layout

```
shared/models/        property.py section.py room.py stay.py event.py   ← DB contract (1 model/file, registered in __init__.py + __all__)
core/exceptions.py    (modify) add ValidationError(422)
supervisor/dal/       sections.py rooms.py stays.py events.py           ← CRUD + event writes (add-only; no flush)
supervisor/services/  sections.py rooms.py stays.py                     ← business logic, domain errors, await s.flush()
supervisor/api/binding.py                                               ← sections+rooms+stays routes; registered in supervisor/api/__init__.py
public/dal/bindings.py   get_active_binding_for_guest()                 ← the one ambient read
public/services/auth.py  (modify) resolve_ambient()                     ← the §6 seam (now on main)
public/schemas/auth.py   (modify) AuthUser += 5 optional ambient fields
public/api/auth.py       (modify) /me builds AuthUser + ambient
```

**API routing matches the merged structure exactly:** sub-routers carry a
short prefix and are composed by `conduit/supervisor/api/__init__.py`
(`router = APIRouter(prefix="/supervisor"); router.include_router(...)`);
`main.py` adds `s.api_prefix` (`/api`). So a new
`conduit/supervisor/api/binding.py` exposes
`router = APIRouter(tags=["supervisor-binding"])` with paths `/sections`,
`/sections/{id}`, `/rooms`, `/rooms/{id}`, `/stays`, `/stays/{id}`,
`/stays/{id}/relocate`, `/stays/{id}/checkout` → resolving to the spec §8
paths `/api/supervisor/...`. **Not** the existing `setup.py` (its router has
a `/setup` prefix and would mis-path everything). Gating is **per-handler**
`actor: Actor = Depends(_sup)` where `_sup = require_roles("supervisor",
"duty_manager")` (mirrors `supervisor/api/accounts.py`), not router-level
`dependencies=`.

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

⚠️ **The one cross-slice touch point (auth is now merged to `main`).** This is
the only place this slice modifies auth-owned code: `public/services/auth.py`
(append `resolve_ambient`), `public/schemas/auth.py` (5 optional fields on
`AuthUser`), `public/api/auth.py` (the `/me` handler builds `AuthUser` +
ambient). The inherited contract-snapshot guard
(`tests/api/test_security_guards.py` + `tests/api/contract_snapshot.json`)
**will go red** on the new routes + changed surface — that is the guard
working. It is regenerated **within this slice** by deleting
`tests/api/contract_snapshot.json` and re-running (the guard recreates then
enforces). No merge gating remains — this lands directly against `main`.

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

- **Already in `components/ui/` on `main` — reuse, do NOT re-add** (re-running
  `shadcn add` overwrites the project's edited copy): alert, alert-dialog,
  avatar, badge, breadcrumb, button, card, collapsible, dialog,
  dropdown-menu, field, input, label, select, separator, sheet, sidebar,
  skeleton, sonner, table, tabs, tooltip.
- **Shared primitives already present — reuse with their real APIs:**
  `@/components/layout/page-header` (`PageHeader{title, description?,
  actions?}` — note `actions`, **not** `action`), `@/components/common/`:
  `empty-state` (`EmptyState{title, hint?, action?}` — **not**
  `description`), `error-state` (`ErrorState{title?, onRetry?}`),
  `data-table-shell` (`DataTableShell{state:"loading"|"error"|"empty"|
  "ready", toolbar?, table, cards, onRetry?, emptyTitle, emptyHint?}` — the
  caller computes `state` and passes a `<Table>` for `table` and a node list
  for `cards`, exactly as `manage-accounts.tsx` does), `confirm`
  (`<Confirm open onOpenChange title description? confirmLabel? onConfirm>`
  — a **controlled component**, not an imperative `await confirm()`),
  `status-badge`, `role-badge`. The API client is `@/lib/api-client` →
  `api.get/post/patch/del` (note `del`, not `delete`).
- **This slice installs (verified absent on `main`):**
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
  - **Check out** → the `<Confirm>` controlled component (state-driven
    `open`/`onConfirm`), exactly the `manage-accounts.tsx` disable pattern —
    **not** an imperative `await confirm(...)`.
  - **Check in guest** `Dialog` — single-column, `max-w` capped: guest
    `combobox-field` (filtered to no-active-stay), room `combobox-field`,
    `date-range-field`; auth's async/skeleton bar.
- **Nav (this slice's wiring):** add a **Sections** item under
  `Setup` (the existing `supervisorNav` "Sections & Rosters" entry →
  point its Sections half here; Rosters stays a next-slice stub);
  **Guest Provisioning** (existing nav entry, `/supervisor/provisioning`)
  → the Check-in page. Routes wired in `App.tsx` + `supervisorNav`.

### Design system & tightness — separate follow-up (NOT this slice)

Auth is merged; the uniformity primitives exist on `main`. This slice
**consumes them as-is and does not retune global tokens** (`index.css`) —
that is a deliberate scope boundary, not a merge gate. A global
tightness pass touches every existing auth page and is its own focused
change; bundling it here would be scope creep and would make this slice's
diff unreviewable. Recorded as a follow-up:

- **Aesthetic:** an operations console (Linear / Vercel-dashboard /
  flight-ops) — calm, dense, precise. Color = meaning only (`destructive`;
  a single operational accent deferred to the awareness/decision surfaces).
- **Tighten geometry:** target `--radius ≈ 0.4rem` (current `0.625rem`
  with xl/2xl/3xl multipliers is pillowy for an ops tool); hairline
  borders; compact controls (`h-9`); denser table rhythm.
- **Hierarchy by weight, not size**; status by weight + a quiet dot, never
  loud pills.
- **Action:** a separate follow-up PR retunes the shared tokens once,
  re-verifying all existing pages. This slice's pages are built to look
  right under both the current and the target tokens.

## 10. Test bench

**Goal & honest boundary.** "Pass ⇒ no manual re-check" is only honest if a
regression *cannot* ship without turning the suite red. The bench is built so
tests are not just examples but **structural guards failing on whole classes
of change** (a new field, a renamed route, a dropped authz check, an untested
branch). The guarantee holds for every documented behaviour **and** these
guarded classes; it is **not** a guarantee against a requirement never
specified. Stated plainly so the comfort is real, not false.

Extends the **real merged harness** (`tests/conftest.py` on `main`): a
session-scoped throwaway `conduit_test` DB built by `alembic command.upgrade
head` (so it includes the 2nd migration automatically); function-scoped async
fixtures `db` (an `AsyncSession`), `client` (`httpx.AsyncClient` +
`ASGITransport`, `db_session` dependency-overridden onto `db`, cookie jar
persists), `make_account(role, username, password="pw-123456", …)` (real
`supervisor.services.accounts.create_account`, commits), `login(username,
password)` (POSTs `/api/auth/login` on `client`). **There is no
`supervisor_client` fixture** — an authed supervisor chain is
`await make_account("supervisor","sup","pw-123456"); await
login("sup","pw-123456")` then use `client`. All tests are `async def`
(`asyncio_mode=auto`). Precondition data via real services, never raw inserts.

**Teardown reality + this slice's required extension.** The merged `db`
fixture's `finally` deletes **only `Account`**. This slice's tables FK to
`account`/`room`/`section`, so an `Account`-only delete FK-fails once stays
exist. This slice **adds `tests/binding/conftest.py`** with an autouse
fixture that deletes the binding tables in **reverse-FK order**
(`event_*`→`event`→`stay`→`room`→`section`; `Property` left as the seeded
singleton) — its `finally` runs *before* the `db` finalizer (pytest LIFO),
so the inherited `Account` delete then succeeds. Plus a `seeded_property`
fixture and a leak sentinel asserting binding tables at baseline between
tests. Tests are written **mechanism-agnostic** (no dependence on
delete-vs-rollback).

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

**Structural guards — what `main` actually has (in
`tests/api/test_security_guards.py`) + what this slice adds:**

*Inherited, auto-covering the new routes (no new code needed):*
1. **Auth-coverage meta-test** — iterates every non-`{param}` `/api` route
   not in `PUBLIC={/api/health,/api/auth/login}` and asserts 401/403 without
   a cookie. The new `/api/supervisor/sections|rooms|stays` are
   **automatically** swept in — an unguarded route fails it.
2. **Contract snapshot** — `tests/api/contract_snapshot.json` is the sorted
   `[method, path]` list; `test_contract_snapshot_matches` fails on *any*
   route-surface drift. Regenerated **intentionally within this slice** by
   deleting the JSON and re-running (the test recreates then enforces). NB:
   the snapshot tracks **routes, not response shapes** — it catches the new
   routes, *not* `/auth/me` field changes.
3. **`secret_hash` never serialized** + **JWT tamper/alg-none rejected** —
   already exercise `/auth/me` and `/supervisor/*`; new responses pass
   through the secret-hash substring guard for free.

*Added by this slice (the real codebase has no response-schema or
role×matrix guard — so this slice supplies the equivalent assurance
explicitly):*
4. **Response-shape assertions** — `SectionOut`/`RoomOut`/`StayOut` are
   pydantic `extra="forbid"`; tests parse every response back through them
   (leaked/dropped field ⇒ red). The **`/auth/me` ambient contract** is
   asserted explicitly by the named invariants (#1/#4) and the e2e
   sentinel — *not* by the route snapshot.
5. **Role × endpoint** — each new route tested for guest/servicer→403,
   no-cookie→401, supervisor/duty_manager→allowed (the per-handler `_sup`
   gate), since no generated matrix exists to inherit.
6. **Coverage gate (real)** — the merged `pyproject.toml` enforces
   `--cov-fail-under=90` (line) over `conduit.public`/`conduit.supervisor`/
   `conduit.core`/`conduit.shared.models`; this slice's modules fall in
   that scope automatically. **No branch/100 claim** — the gate is the
   existing global 90% line gate; do not silently change it (it would move
   the bar for all merged auth code too).
7. **Leak sentinel** — between tests assert binding tables at baseline
   (`section/room/stay/event = 0`). A missed teardown fails **loudly**.

**End-to-end journey sentinel (the test you actually trust):** one scripted
test that *is* this slice's journey — seed supervisor → create section+room
→ create guest (auth service) → check-in → guest `GET /auth/me` shows
ambient → **relocate** → same guest's next `/auth/me` shows new
room+section (**no re-login**) → reassign the room's section → ambient
section follows (**no `Stay` write**) → checkout → `/auth/me` ambient
`null` → re-check-in allowed. Breaks loudly if any pipeline stage
regresses.

**Isolation / zero-residue.** The merged harness uses model-delete in the
`db` fixture's `finally` (runs on pass/fail/exception). This slice's
`tests/binding/conftest.py` extends that with the FK-ordered binding delete
described above, so zero-residue-on-failure holds for the new tables too.
Transactional savepoint-rollback (faster, ordering-free) is noted as an
**optional separate harness follow-up** against `main` — *not* part of this
slice, and not required since the delete teardown already guarantees no
residue. Tests stay mechanism-agnostic so that follow-up needs no change
here.

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
9. Contract snapshot regenerated (deleted + recreated) to include the new
   `/api/supervisor/sections|rooms|stays*` routes — green *because*
   intentionally regenerated, not bypassed. (`/auth/me` is not a new route;
   its ambient contract is covered by #1/#4 + the e2e sentinel, since the
   snapshot tracks routes, not response shapes.)

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
  policy) — a **separate follow-up PR against `main`** (auth is merged; not
  a merge gate). Out of this slice to keep its diff reviewable; its pages
  are built to look right under both current and target tokens (§9).
- **Test-isolation upgrade to savepoint-rollback** — optional separate
  harness follow-up against `main` (§10). Not required (delete teardown
  already gives zero-residue); tests are mechanism-agnostic so it needs no
  change here.
