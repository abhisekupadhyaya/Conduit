# Conduit

An AI-driven, **self-contained, single-property guest-request orchestrator**.

A guest asks for something in plain text. Conduit understands it, splits a
multi-part ask into independent sub-requests, triages each mechanically,
routes it straight to the accountable person, owns the full task lifecycle
(timers, stalls, escalation, closure), keeps the guest informed, and surfaces
only exceptions to a human supervisor who acts as a *time-boxed checkpoint —
never a bottleneck*. Management gets a live operational view.

The human who does the physical work stays human. The human coordination
layer that decided *who* does it and *when* is what Conduit replaces.

## Status

**Core lifecycle is implemented and tested; behaviour is being filled in
slice by slice.** The in-process timer engine, the dispatch & escalation
spine, routing, triage classification, staffing/availability, and the auth
slice are built and covered by an end-to-end test suite — including a
scripted full-journey test and structural auth/event-log guards. ORM models
for the spine are in place. A few paths remain deliberate
`NotImplementedError` stubs (multi-part request decomposition, the servicer
queue endpoint, parts of supervisor setup).

| Area | State |
|---|---|
| Product scope & decisions | Defined (the source of truth) |
| Infrastructure architecture | Converged — see [docs/archi/](docs/archi/) |
| Data model | Spine modelled; still evolvable — see [docs/datamodels/](docs/datamodels/) |
| Frontend | Scaffolded + role-routed portals (Vite/React/TS/Tailwind/shadcn) |
| Backend | Engine + dispatch spine + staffing + auth implemented (FastAPI, engine in-process) |
| Deployment | Terraform IaC + deploy scripts — see [dev-ops/](dev-ops/) |
| Feature behaviour | Largely implemented; a few documented stubs remain |

## Repository layout

```
backend/    FastAPI — 4 portal slices (guest/servicer/supervisor/public)
            + shared/ (db · models · events · domain · engine · integrations);
            the lifecycle engine runs in-process (single deployable)
frontend/   One React SPA — shared shell, role-routed per portal;
            all API via TanStack Query (auth is the only direct exception)
docs/       architecture (archi/) + data models (datamodels/)
            + superpowers/ (per-slice design specs & implementation plans)
dev-ops/    Terraform IaC + deploy/migrate/seed/secrets scripts (AWS)
```

Full intended structure and rationale:
[docs/archi/code-structure.md](docs/archi/code-structure.md).

## Running locally

Local dev expects a Postgres and a MinIO (the RDS / S3 alternatives) reachable
on the Docker network by service name (`postgres:5432`, `minio:9000`).

### Backend

```bash
cd backend
.venv/bin/uvicorn apps.api_main:app --reload --port 8000
# (.venv already created; otherwise: python3.12 -m venv .venv
#  && .venv/bin/pip install -e ".[dev]")
.venv/bin/pytest -q                       # tests
```

Config is env-driven (`CONDUIT_*`); copy `backend/.env.example` → `backend/.env`
and adjust. The API is served under `/api` with CORS enabled for the SPA
origin (a conscious divergence from the Amplify same-origin proxy — see
[docs/archi/decisions.md](docs/archi/decisions.md) AD6).

### Frontend

```bash
cd frontend
npm install
npm run dev        # dev server (Vite, port 5173)
npm run build      # typecheck + production build
```

`VITE_API_BASE` (in `frontend/.env`, default `http://localhost:8000/api`)
points the SPA at the backend.

## Documentation

Start at [docs/](docs/). Read order: the product scope/decisions, then
[docs/archi/](docs/archi/) (how it runs), then
[docs/datamodels/](docs/datamodels/) (the entities those decisions imply).

## Principle

The product promise is *"nothing is silently lost."* That durability lives in
the database state machine and its timers — not in redundant infrastructure —
which is why the data model and the timer engine are treated as the most
load-bearing parts of this system.
