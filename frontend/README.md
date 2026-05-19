# Conduit — Frontend

One React SPA serving all three portals (guest / servicer / supervisor),
role-routed to a **shared shell**. Project context:
[../README.md](../README.md); architecture:
[../docs/archi/](../docs/archi/).

## Stack

- **Vite + React + TypeScript**
- **Tailwind CSS v4** + **shadcn/ui** (radix-nova), light/dark/system theme
- **React Router** — role-based routing
- **TanStack Query** — server state

## Conventions

- **All backend calls go through TanStack Query** — `useQuery` for reads
  (live surfaces poll; the product's real-time model is polling-first),
  `useMutation` for writes — in `src/shell/<portal>/hooks/`, over
  `src/lib/api-client.ts`. **The only exception is auth** (login/logout),
  which is a direct call in `src/auth/auth-provider`.
- **One shared shell** (`src/components/layout/`); the only per-portal
  difference is `src/shell/<portal>/nav.tsx`.
- The theme switcher (light/dark/system) lives in the shared `nav-user`.

## Layout

```
src/
  main.tsx          ThemeProvider → QueryClient → Router → Auth → Tooltip
  App.tsx           role-routed; one shared shell per route
  auth/             use-auth, auth-provider, require-auth, login-form/page
  lib/              api-client, query-client, role-routing, utils
  public/           landing (auth-aware redirect)
  hooks/            shared hooks
  components/
    ui/             shadcn primitives
    theme-provider.tsx
    layout/         shared shell: app-shell, app-sidebar, nav-main,
                    nav-user, app-brand, nav-config, page-header
    common/         cross-portal domain widgets (composer, countdown,
                    shift-card, status/role badges, form dialogs, …)
  shell/
    guest/          nav · index · settings · pages/ · hooks/
                      (conversation thread, submit, confirm)
    servicer/       nav · index · settings · pages/ · hooks/
                      (shift card, task queue, accept/start/complete/escalate)
    supervisor/     nav · index · settings · pages/ (~15: awareness,
                    decisions, task-explorer, sections, issue-codes,
                    staff, rosters, knowledge-base, sla-presets,
                    escalation-ladder, provisioning, manage-*) · hooks/
```

## Develop

```bash
npm install
npm run dev        # Vite dev server on :5173
npm run build      # typecheck (tsc -b) + production build
npm run lint
```

Requires Node 18+ (developed on Node 24).

## Environment

`VITE_API_BASE` — absolute base URL of the backend API.

- local: `http://localhost:8000/api` (default in `.env`)
- prod : `https://api.<domain>/api`

Copy `.env.example` → `.env.local` to override. An absolute cross-origin base
means the backend must send CORS headers (a conscious divergence from the
Amplify same-origin proxy — see
[../docs/archi/decisions.md](../docs/archi/decisions.md) AD6).

## Status

Built out. All three role portals (guest / servicer / supervisor) have real
pages, per-portal hooks, and data binding over TanStack Query, with
loading/empty/error states throughout. Backend behaviour is largely landed;
the few surfaces fed by the remaining backend stubs (servicer queue, the
supervisor config-read) render their empty/loading states until those land.
