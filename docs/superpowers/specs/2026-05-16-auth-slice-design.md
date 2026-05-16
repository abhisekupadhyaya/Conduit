# Auth Slice — Design

| | |
|---|---|
| **Status** | Approved design (2026-05-16) |
| **Scope** | First buildable vertical: identity + session for all three portals |
| **Source of truth** | Product decisions (D-series) — *what*; this doc — *shape of this slice* |

## 1. Why this slice first

Every journey in the product begins with an authenticated actor; nothing
downstream (intake, triage, routing, the engine) can be exercised end-to-end
without identity and sessions. The data-model docs tag `account` as the most
stable IDENTITY entity, so it is safe to commit firmly now. This slice turns
the scaffold's stub auth into a working, role-routed login and gives the
supervisor the ability to provision everyone else (D3a: nobody self-registers).

The slice is deliberately **identity only** — it is the root the next slice
(guest ↔ room/stay binding) and all later flows build on.

## 2. Scope

**In**

- `account` — the first real ORM model + the first Alembic migration.
- Cookie-session login for all three portals through one shared login page.
- `GET /auth/me` session rehydrate; `POST /auth/logout`.
- Supervisor-managed account CRUD (create / list / disable / rename / reset).
- Idempotent seed for the bootstrap supervisor.
- Shared **Settings** entry in the user menu, present in every portal.
- Supervisor pages: **Settings** (self + add other supervisor-portal users),
  **Manage Servicers**, **Manage Guests**.

**Out (next slice / later, by decision not omission)**

- Stay / Room / Section binding. A guest created here has credentials but no
  room. Room binding is a separate concern with its own provisioning surface
  and is the precondition the conversation flow depends on — it is the
  immediate next slice.
- Servicer roster / skills / availability (`staff_profile`) — belongs to the
  routing slice (D12/D18/D39).
- RBAC — out of product scope; three fixed roles via a coarse gate (AD10).

## 3. Data model (firm commitment)

One table, `account` (IDENTITY — most stable group):

| Field | Notes |
|---|---|
| `id` | pk |
| `role` | `guest \| servicer \| supervisor \| duty_manager` |
| `username` | unique; the login identifier |
| `secret_hash` | argon2 (new dependency — none in the scaffold today) |
| `display_name` | shown to guests in status ("… is on her way", D17) |
| `status` | `active \| disabled` |
| `created_at` / `updated_at` | |

**Decision — disable, never delete (D29).** Accounts are persistent and never
torn down; deprovisioning is a `status` flip to `disabled`. *Rejected:* hard
delete (loses the D29 persistent-account guarantee and orphans future history).

This is the first entry in the currently-empty `shared/models/` and the first
Alembic version.

## 4. Session & transport decisions

**Decision — httpOnly cookie session.** Login sets an httpOnly cookie carrying
the existing JWT (`issue_token` is already implemented); the SPA sends nothing
explicit (`credentials:"include"` is already set in the api-client). `Secure`
is env-driven (off for plain-http localhost, on in prod); `SameSite=Lax`
(SPA and API are same registrable domain, cross-origin — Lax is sufficient and
permits the login POST). CORS allows credentials for the explicit SPA origin,
never `*` (backend owns CORS — the conscious AD6 divergence).

*Rejected:* bearer token in `localStorage`. It was the smaller change and
matched the scaffold's `HTTPBearer`, but a JS-readable token is a worse
default; the cookie keeps the token out of JS. Consequence accepted: `deps.py`
moves off `HTTPBearer` onto cookie extraction, and CSRF risk is bounded by
`SameSite=Lax` for a single-property pilot (broader abuse/CSRF hardening is
already out of v1 scope, D27).

## 5. Backend surface

- `core/security.py` — add cookie set/clear helpers; keep `issue_token` /
  `decode_token`.
- `core/deps.py` — `current_actor` resolves the `Actor` from the cookie
  (replaces `HTTPBearer`); existing `require_roles` gate unchanged.
- `core/config.py` — add `cookie_name`, `cookie_secure` (env-driven).
- `core/middleware.py` — CORS: credentials + explicit origin (via the existing
  `cors_origins` setting).
- `public/api/auth.py` — real `POST /auth/login` (verify argon2, set cookie),
  `POST /auth/logout` (clear cookie), `GET /auth/me` (rehydrate).
- `supervisor/api/accounts.py` (new) — `GET /supervisor/accounts?role=`,
  `POST /supervisor/accounts`, `PATCH /supervisor/accounts/{id}`
  (disable / rename / reset password). Gated to supervisor + duty_manager.
- Seed — `python -m conduit.seed`, idempotent, reads
  `CONDUIT_SEED_SUPERVISOR_USERNAME` / `_PASSWORD`, creates the supervisor
  only if absent.

## 6. Frontend surface

- `auth/auth-provider.tsx` — replace the fake localStorage / role-from-prefix
  stub: `login` → `POST /auth/login` then `GET /auth/me`; rehydrate via
  `/auth/me` on mount; `logout` → `POST /auth/logout`. No token in JS.
- `lib/api-client.ts` — keep `credentials:"include"`; a 401 from `/auth/me`
  means logged-out.
- `components/layout/nav-user.tsx` — add a **Settings** item above Log out,
  linking to the current portal's settings route. Shared across all portals.
- `shell/supervisor/pages/` (new) —
  - `settings.tsx` — own account + add other supervisor-portal users
    (supervisor / duty_manager).
  - `manage-servicers.tsx` — list / create / disable servicer accounts.
  - `manage-guests.tsx` — list / create / disable guest accounts
    (credentials only; UI notes "no room assigned yet").
- `shell/guest/settings.tsx`, `shell/servicer/settings.tsx` — minimal own-account
  page so the shared Settings link resolves in every portal.
- `App.tsx` + `supervisorNav` — wire the new routes; per-portal data hooks in
  `shell/<portal>/hooks/` via TanStack Query (the established pattern).

## 7. Verification bar ("done" means)

- Alembic migration applies cleanly from empty.
- `python -m conduit.seed` is idempotent (safe to run twice).
- Seeded supervisor logs in on the shared page → lands on `/supervisor`.
- Supervisor creates a servicer and a guest; each logs in on the same page →
  role-routed to its portal; a wrong-portal URL bounces (existing
  `RequireAuth`).
- Logout clears the cookie; SPA reload stays logged in via `/auth/me`.
- Backend tests cover: login success/failure, `/auth/me`, logout,
  role-gated account CRUD, and the disable-not-delete path.

## 8. Open / deferred (named, not silent)

- Stay/Room/Section binding — the immediate next slice.
- `staff_profile` (roster/skills/availability) — the routing slice.
- Password-reset UX beyond supervisor reset, email, lockout/rate-limit —
  out of v1 (consistent with the D27 trust boundary).
