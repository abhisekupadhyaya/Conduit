# Conduit — Backend

FastAPI backend, **single deployable**: the lifecycle engine runs in-process
(AD4), not as a second service. Project context: [../README.md](../README.md);
architecture: [../docs/archi/](../docs/archi/); data model (deliberately soft):
[../docs/datamodels/](../docs/datamodels/).

## Stack

- **Python 3.12 + FastAPI**
- **SQLAlchemy 2 (async) + asyncpg + Alembic**
- **Pydantic / pydantic-settings** — typed env config
- **PyJWT** — app-managed sessions (AD8)
- **boto3** — S3 / MinIO · **httpx + tenacity** — bulkheaded OpenAI (AD11)

## Conventions

- The four portal slices (`guest/ servicer/ supervisor/ public/`) are the
  **only** places with `api/ services/ dal/ schemas/`.
- `engine/` lives under `shared/` (cross-portal runtime machinery).
- Triage is **not** a slice — it's shared *domain* logic
  (`shared/domain/`), triggered from `guest/services/intake.py`.
- `dal/` is the only layer that touches the DB; the append-only event log is
  the single source the awareness/analytics read-models build on.

## Layout

```
apps/api_main.py          uvicorn entry → conduit.main:app
conduit/
  main.py                 app composition + in-process engine lifespan
  core/                   config · deps · security (JWT, AD8) · middleware · exceptions
  guest/ servicer/        the only vertical slices — each:
  supervisor/ public/       api/ · services/ · dal/ · schemas/
  shared/
    db.py  models/        async SQLAlchemy + ORM (entities land here)
    events/               append-only event log (the observability spine)
    domain/               triage · routing · lifecycle  (cross-portal mechanism)
    engine/               runner · timers · spine · sweeper  (the lifecycle core)
    integrations/         openai (bulkheaded, AD11) · storage (S3/MinIO)
migrations/               alembic (URL + metadata from settings)
tests/                    api · domain · engine · smoke
```

## Develop

```bash
# .venv already created; otherwise:
#   python3.12 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/uvicorn apps.api_main:app --reload --port 8000
.venv/bin/pytest -q                  # tests
.venv/bin/alembic upgrade head       # once models exist
```

Requires Python 3.12.

## Environment

Config is env-driven (prefix `CONDUIT_`); copy `.env.example` → `.env`.

| Var | Purpose | Local default |
|---|---|---|
| `CONDUIT_DATABASE_URL` | Postgres (the RDS alternative) | `postgresql+asyncpg://…@postgres:5432/…` |
| `CONDUIT_S3_ENDPOINT_URL` | MinIO (the S3 alternative) | `http://minio:9000` |
| `CONDUIT_API_PREFIX` | API mount path | `/api` |
| `CONDUIT_CORS_ORIGINS` | allowed SPA origin | `http://localhost:5173` |
| `CONDUIT_OPENAI_*` | LLM (bulkheaded) | model `gpt-5.4-mini` |

Postgres/MinIO are reached **by service name on the internal port** (Docker
network), not the host-published ports. The API is served under `/api` with
CORS enabled for the SPA origin — the conscious AD6 divergence (backend owns
CORS instead of an Amplify same-origin proxy).

## Status

Core implemented and tested. The in-process timer engine
(`shared/engine/`), the dispatch & escalation spine, routing, triage
classification (`shared/domain/`), staffing/availability, and the auth slice
are built; spine ORM models exist; `tests/` includes a scripted full-journey
end-to-end plus structural auth/event-log guards. A few paths remain
deliberate `NotImplementedError` stubs — multi-part decomposition
(`triage.decompose`/`triage`; `triage.classify` *is* implemented), the
servicer queue endpoint, and parts of `supervisor/api/setup.py`. The data
model is still marked *subject to change* where flagged.
