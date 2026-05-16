# Auth Slice — Design

| | |
|---|---|
| **Status** | Approved design (2026-05-16) |
| **Scope** | First buildable vertical: identity + session for all three portals |
| **Source of truth** | Product decisions (D-series) — *what*; this doc — *shape of this slice* |

## 1. Why this slice first

Every journey begins with an authenticated actor; nothing downstream (intake,
triage, routing, the engine) can be exercised end-to-end without identity and
sessions. The data-model docs tag `account` as the most stable IDENTITY
entity, so it is safe to commit firmly now. This slice turns the scaffold's
stub auth into working, role-routed login and gives the supervisor the ability
to provision everyone else (D3a: nobody self-registers). It is deliberately
**identity only** — the root the next slice (guest ↔ room/stay binding) and
all later flows build on.

## 2. Scope

**In:** `account` (first real ORM model) + first Alembic migration;
cookie-session login via one shared login page for all three portals;
`GET/PATCH /auth/me`, `POST /auth/logout`; supervisor-managed account CRUD
(create / list / disable / rename / reset — no delete); idempotent bootstrap
supervisor seed; shared **Settings** entry in the user menu in every portal;
supervisor pages **Settings** (self + add supervisor-portal users), **Manage
Servicers**, **Manage Guests**; the shared UI/uniformity layer applied to the
pages this slice ships; a comprehensive backend test bench.

**Out (next slice / later, by decision not omission):** Stay / Room / Section
binding (the immediate next slice — a guest created here has credentials but
no room); servicer roster / skills / availability `staff_profile` (the routing
slice, D12/D18/D39); RBAC (out of product scope; three fixed roles via a
coarse gate, AD10).

## 3. Decision ledger

| Area | Locked decision |
|---|---|
| Model | One `account` table; `uuid` pk; `role`/`status` = text + CHECK; unique on `lower(username)`; `secret_hash` NOT NULL; no `email`. Resolves datamodels **Q1** = unified account |
| Session | httpOnly cookie, `SameSite=Lax`, `Secure` env-driven; JWT (existing `issue_token`); bcrypt via passlib; hashing helper in `core/security.py` |
| Errors | Add `ConflictError(409)` to `core/exceptions.py` (others already exist); services raise domain errors, never `HTTPException` |
| API | `POST /auth/login` (returns user + sets cookie), `POST /auth/logout`, `GET /auth/me`, `PATCH /auth/me`; `GET/POST/PATCH /supervisor/accounts`; **no DELETE** (D29); login + `/auth/me` re-check `status==active`; lockout guards → 409 |
| Layering | `api → services → dal → models`; ORM up; schema mapping at the API layer only; commit at the request edge, services `flush` never `commit` |
| DAL ownership | `public/dal/accounts.py` owns account persistence; `supervisor` services import it (one-directional). Recorded as a one-line note in `code-structure.md` |
| Hooks | Auth (login/logout/me/refresh) direct in `auth-provider` (the documented exception); one parameterized `use-accounts`; shared `useUpdateSelf`; centralized 401 → logout |
| UI | shadcn added via CLI then edited; pure-monochrome (remove stray dark `--sidebar-primary` indigo); 5 shared primitives; bounded cleanup |
| Responsive | Role-differentiated: guest/servicer mobile-first, supervisor desktop-first but graceful to phone; tables reflow to cards `< md`; responsive Dialog; single-column forms; capped content widths |
| Async | App-boot splash gating `/auth/me`; bespoke skeletons mirroring final layout; skeleton on first load only + keep-previous-data on refetch; optimistic only for enable/disable; `error-state` primitive; ~180ms skeleton delay |
| Test bench | Throwaway `conduit_test` DB (alembic-built, session-dropped); per-test teardown deletes via the **model** (`delete(Account)`) in a `finally`; precondition data via the real `create_account` service; leak sentinel; 5 structural guards; coverage gate; CI needs Postgres, red blocks merge |

## 4. Data model — `account` (IDENTITY)

`conduit/shared/models/account.py`, registered in `shared/models/__init__.py`
so Alembic autogenerate sees it (the first Alembic version creates this one
table).

| Column | Type | Notes |
|---|---|---|
| `id` | `uuid` pk | stable join target for all later entities (`staff_profile.account_id`, `stay.guest_account_id`, `event.actor_account_id`) |
| `role` | `text` + CHECK | `guest \| servicer \| supervisor \| duty_manager` |
| `username` | `text`, not null | unique on `lower(username)` (case-insensitive) |
| `secret_hash` | `text`, not null | bcrypt/passlib; never serialized |
| `display_name` | `text`, not null | shown to guests in status (D17) |
| `status` | `text` + CHECK, default `active` | `active \| disabled` — D29: disable, never delete |
| `created_at` | `timestamptz`, default `now()` | |
| `updated_at` | `timestamptz`, `onupdate now()` | |

**Resolves datamodels Q1** ("unified account vs split Guest/Staff") = unified.
Forward-compatible without migration: deferred `staff_profile` →
`account_id pk fk` (1:1, servicer-only); deferred `stay` →
`guest_account_id fk` (guest-only). Locking `account.id` as `uuid` now is what
makes that true. `text + CHECK` over PG `enum` keeps rule changes from
migrating data (datamodels principle: structure permissive, mechanism in
code).

## 5. Session, security, errors

httpOnly cookie carries the JWT from the existing `issue_token`. `SameSite=Lax`
(SPA and API share a registrable domain, cross-origin — Lax suffices and
permits the login POST). `Secure` is env-driven (off for plain-http localhost,
on in prod). CORS allows credentials for the explicit SPA origin, never `*`
(backend owns CORS — the conscious AD6 divergence).

- `core/security.py` — add `set_session_cookie` / `clear_session_cookie` and
  `hash_password` / `verify_password` (bcrypt/passlib; guard the bcrypt
  72-byte input cap). Keep existing `issue_token` / `decode_token`.
- `core/deps.py` — `current_actor` resolves the `Actor` from the cookie
  (replaces `HTTPBearer`); existing `require_roles` gate unchanged.
- `core/config.py` — add `cookie_name`, `cookie_secure` (env-driven).
- `core/exceptions.py` — add `ConflictError` (409); existing handler shape
  `{"error","message"}` unchanged.
- **Invariant:** `authenticate` and `GET /auth/me` reject a structurally valid
  token whose account is `disabled` (status re-checked every request, not
  trusted from the token).

## 6. Backend layering & API

`api → services → dal → models`. API authenticates the caller, parses the
request schema, calls one service function, maps the returned ORM model to a
response schema, sets/clears the cookie. No business logic in handlers.
Transactions commit at the request edge (the `db_session` dependency); services
`flush`, never `commit`. ORM instances travel up; pydantic mapping happens only
at the API layer.

**DAL** (`public/dal/accounts.py`, imported by `supervisor` services) —
`get_by_username` (case-insensitive), `get_by_id`, `list_accounts(role?,
status?)`, `insert_account`, `update_account`, `count_active_by_role`. Pure
SQL; no hashing, no rules.

**Services** —
`public/services/auth.py`: `authenticate`, `current_account`, `update_self`.
`supervisor/services/accounts.py`: `list_accounts`, `create_account`,
`update_account`. Business logic only (hashing, role-allowed checks, "verify
current password before change", lockout guards). No FastAPI/HTTP types;
returns ORM models.

**Endpoints**

- `POST /api/auth/login` `{username,password}` → `200 {id,role,display_name}` +
  Set-Cookie; bad credentials / unknown / disabled → `401`, identical body, no
  Set-Cookie; missing fields → `422`.
- `POST /api/auth/logout` → `204`, cookie cleared.
- `GET /api/auth/me` → `200 {id,role,username,display_name}`; missing /
  invalid / expired / disabled-account → `401`.
- `PATCH /api/auth/me` `{display_name?,current_password?,new_password?}` →
  `200` user; password change requires correct `current_password`
  (wrong → `401/403`); unauthenticated → `401`.
- `GET /api/supervisor/accounts?role=&status=` → `200 AccountOut[]`.
- `POST /api/supervisor/accounts` `{role,username,display_name,password}` →
  `201 AccountOut`; duplicate username → `409`; disallowed role → `422`. All
  four roles creatable; the three UI surfaces pre-filter `role`.
- `PATCH /api/supervisor/accounts/{id}` `{display_name?,status?,password?}` →
  `200 AccountOut`; unknown id → `404`; lockout guards (disable self, disable
  or role-demote the last active supervisor) → `409`.
- No `DELETE` route (D29 — `DELETE` returns `405`, asserted as an invariant).

Gating: every `/supervisor/*` route admits only `supervisor` + `duty_manager`
(shared surface); guest/servicer → `403`; no cookie → `401`. Server-side
`require_roles` enforced regardless of the client-side `RequireAuth`.

**Shapes:** `AuthUser{id,role,username,display_name}`,
`AccountOut{id,role,username,display_name,status,created_at}`. `secret_hash`
never serialized.

## 7. Frontend — hooks

Convention (`code-structure.md`): all API access via TanStack Query in
`shell/<portal>/hooks/`, **except login/logout** which stay direct in
`auth-provider`.

- `auth/auth-provider.tsx` — replace the fake localStorage stub. Direct calls:
  `login` → `POST /auth/login` (sets `user` from the response); bootstrap on
  mount → `GET /auth/me`; `logout` → `POST /auth/logout`; `refreshUser()`
  exposed on context. Session is one source of truth (context), never the
  query cache. Nothing stored in JS (cookie is httpOnly).
- `shell/supervisor/hooks/use-accounts.ts` — one parameterized module for all
  three supervisor pages: `useAccounts(role?,status?)` (query),
  `useCreateAccount` / `useUpdateAccount` (mutations, invalidate
  `['accounts']`).
- `auth/use-update-self.ts` — shared `useUpdateSelf` (TanStack mutation,
  `PATCH /auth/me`); on success calls context `refreshUser()`.
- `lib/api-client.ts` — keep `credentials:"include"`; one registered
  `onUnauthorized` callback on any 401 → `auth-provider` clears `user` +
  redirects to `/login` (centralized).
- Account list is **not polled** (unlike the AD7 decision queue): default
  `staleTime` + refetch-on-focus.

## 8. Frontend — components & UI

The system is `radix-nova` / `neutral` / Geist / lucide / monochrome OKLCH.
Lean into the control-room aesthetic.

**Token cleanup:** remove the stray chromatic dark `--sidebar-primary`
(indigo) — pure monochrome; status conveyed by weight/fill, not hue
(`destructive` stays). A brand accent is deferred to the operational surfaces
(awareness stream / decision queue) where colour carries meaning.

**Install via `npx shadcn@latest add` then edit:** `card`, `form`
(+ `react-hook-form`, `zod`, `@hookform/resolvers`), `table`, `dialog`,
`alert-dialog`, `sonner` (+ `sonner`), `badge`, `select`, `alert`, `tabs`.
**Reuse:** button, input, label, field, separator, avatar, dropdown-menu,
sidebar, sheet, skeleton, tooltip, breadcrumb, collapsible.

**Shared primitives (the uniformity layer):**
`layout/page-header.tsx`, `common/empty-state.tsx`, `common/error-state.tsx`,
`common/status-badge.tsx` + `role-badge.tsx`, `common/confirm.tsx`
(AlertDialog wrapper), `common/data-table-shell.tsx` (toolbar + table/card
presentations + loading/empty/error). Manage Servicers and Manage Guests are
the same component parameterized by role.

**Cleanup boundary:** introduce the primitives + token fix and apply them to
*only* the pages this slice ships (login, landing, 3 settings, 2 manage) plus
retrofit the 3 existing placeholder shells (`SupervisorHome`, guest, servicer)
onto the primitives. Not touching unbuilt feature pages.

**Pages:**
- **Login** — full-viewport, centered `Card` ~380px, brand mark, username,
  password (quiet show/hide), full-width primary `Button` with inline spinner.
  Failure = one subtle destructive `Alert` ("Incorrect username or password" —
  never which field). No signup / no forgot-password, with one deliberate
  line: *"Accounts are created by your administrator."* (D3a as a statement,
  not a missing feature).
- **Manage Servicers / Guests** — `PageHeader` + count + "Add" `Dialog`; one
  toolbar row (status filter + client-side search); `data-table-shell`:
  avatar+name · username · role `Badge` · status `Badge` · created · `⋯`
  (Rename / Reset password / Enable·Disable). Disable → `confirm`. Skeleton
  rows on first load; `EmptyState`/`ErrorState` otherwise.
- **Settings (all portals, via nav-user gear)** — `Tabs`: Profile (display
  name editable, username read-only, role badge), Password (zod-validated).
  Supervisor additionally gets a **Team** tab (the same `data-table-shell`
  scoped to supervisor/duty_manager). Guest/servicer: Profile + Password only.
  One component, role-driven tab set.
- `nav-user.tsx` gains a **Settings** item (gear) above Log out, linking to
  the current portal's settings route — shared across all portals.
- `App.tsx` + `supervisorNav` wire the new routes.

## 9. Responsive

Role-differentiated. Guest/servicer **mobile-first**; supervisor
**desktop-first but graceful to phone** (duty manager checks it on a phone).
Breakpoints: Tailwind `sm/md/lg`.

- Login: full-bleed `p-4` under `sm`, fixed ~380px centered `≥ sm`.
- `data-table-shell`: `Table` `≥ md`; **stacked card list `< md`** (same data,
  same hooks) — never horizontal-scroll a table. Toolbar one row `≥ sm`,
  stacked `< sm`.
- Settings `Tabs` strip horizontally scrollable `< sm`; forms
  **single-column at every breakpoint**; content capped `max-w-2xl`.
- Create/edit = one responsive `Dialog` (full-width minus gutters `< sm`,
  centered modal `≥ sm`). Bottom-Sheet-on-mobile deferred to a polish pass.
- Shell pages capped `max-w-6xl` centered; full-bleed with padding on small.
- Interactive targets ≥ 44px on coarse pointers (via a `pointer:coarse` rule,
  not per-component).

## 10. Async / loading states

Every async surface has loading / empty / error / success, plus mutation
pending (not a skeleton).

- **App-boot splash** gates `/auth/me` on first paint (prevents the
  login→portal flash introduced by real network auth) — a correctness fix.
- Skeletons are **bespoke, mirroring the final layout** (table-row and
  card-list skeletons in `data-table-shell`; `SettingsSkeleton`) → zero layout
  shift. **Skeleton on first load only** (`isLoading`); on refetch/filter
  (`isFetching`) keep previous data with a subtle cue. ~180ms show-delay to
  suppress flash on fast responses.
- Mutations never skeleton: submit = disabled + spinner + label swap.
  Enable/disable = **optimistic** with rollback + error toast. Create / rename
  / reset = await + success toast (not optimistic).
- `error-state.tsx` (retry → `refetch`) is distinct from `empty-state`. 401 is
  handled by the centralized logout, not rendered here.

## 11. Test bench (comprehensive, regression-proof)

**Infrastructure (`conftest.py`):** dedicated `conduit_test` DB created via
`alembic upgrade head` at session start (the migration is itself under test)
and **dropped at session end**. Per-test teardown deletes via the **model** —
`delete(Account)` through the test session in a `finally` (runs on pass, fail,
or exception); no inverse service exists (D29) so cleanup uses the model the
same way the DAL does, not raw SQL. Precondition data is built through the
**real `create_account` service**, never raw inserts. Test settings:
fixed `jwt_secret`, `cookie_secure=False`, **`engine_enabled=False`**.
`client` = `httpx.AsyncClient(ASGITransport(app))` with `db_session`
overridden onto the test session; cookie jar persists for authed chains.

**Layered tests:** migration up/down round-trip + constraint enforcement;
DAL (case-insensitive lookup, filters, integrity, `count_active_by_role`);
services (every branch incl. all lockout guards and no-enumeration);
API (full stack, cookie flags, role × endpoint matrix, end-to-end
create→login, disable→login-blocked, `DELETE → 405`).

**Five structural guards (close regression *classes*):**
1. **Auth-coverage meta-test** — every route not in an explicit public
   allowlist returns `401` without a cookie.
2. **Contract snapshot** — committed `{path,methods,auth,status}` from the
   OpenAPI schema; any drift fails until intentionally updated.
3. **Response-schema parsing** — every response parsed into an
   extra-forbidden pydantic model (catches leaked *or* dropped fields, e.g.
   `secret_hash`).
4. **Parametric role × endpoint matrix** — authz expectations generated over
   all supervisor routes × all roles, so new routes are auto-covered.
5. **Coverage gate** — `--cov` `fail-under` scoped to the auth/account
   modules; an untested branch fails the suite.

**Leak sentinel:** between modules assert `account` is at seeded baseline — a
missed teardown fails loudly instead of giving false confidence.

**Tested invariants (named, one test each):** D29 no-delete + disable enforced
at login; no user enumeration (identical status+body for unknown-user vs
wrong-password); `secret_hash` never serialized anywhere; the three lockout
guards; cookie flags (HttpOnly / SameSite=Lax / Secure-by-env);
disabled-token-holder rejected at `/auth/me`.

**CI:** a Postgres service is required; a red suite (incl. the coverage gate)
blocks merge.

**Honest boundary:** "pass ⇒ no manual re-check" holds for every documented
behaviour and these structural classes; it is not a guarantee against an
unspecified requirement. The guards make it structurally impossible for an
endpoint, field, or branch to change or ship unguarded without the suite going
red.

## 12. Verification bar ("done" means)

Migration applies from empty and round-trips; `python -m conduit.seed` is
idempotent and fail-fast on missing env creds; the seeded supervisor logs in
on the shared page → `/supervisor`; the supervisor creates a servicer and a
guest, each logs in on the same page → role-routed, wrong-portal URL bounces;
disable blocks that user's next login, re-enable restores it; logout clears
the cookie; SPA reload stays logged in via `/auth/me`; the full test bench
(layered tests + 5 structural guards + leak sentinel + coverage gate) is green.

## 13. Open / deferred (named, not silent)

- Stay / Room / Section binding — the immediate next slice.
- `staff_profile` (roster / skills / availability) — the routing slice.
- Bottom-Sheet-on-mobile for create/edit; a brand accent for operational
  surfaces — later design passes.
- Password reset beyond supervisor-set, email, lockout/rate-limit — out of v1
  (consistent with the D27 trust boundary).
