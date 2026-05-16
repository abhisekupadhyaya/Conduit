# Conduit — Backend

FastAPI backend. **Single deployable**: the lifecycle engine runs in-process
(AD4), not as a second service. Architecture lives in
[../docs/archi/](../docs/archi/); the data model (deliberately soft) in
[../docs/datamodels/](../docs/datamodels/).

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
    domain/               triage · routing · lifecycle  (cross-portal mechanism;
                          NOT a slice — triggered from guest/services/intake.py)
    engine/               runner · timers · spine · sweeper  (the lifecycle core)
    integrations/         openai (bulkheaded, AD11) · storage (S3/MinIO)
migrations/               alembic (URL+metadata from settings)
tests/                    api · domain · engine · smoke
```

Note: there is no `triage/` slice and no `services/dal/schemas` outside the
four portals — triage is shared *domain* logic, and `engine/` lives under
`shared/`.

## Local dev

Backend reaches the docker-compose **Postgres** (RDS alternative) and **MinIO**
(S3 alternative) by **service name on the internal port**:

```
CONDUIT_DATABASE_URL=postgresql+asyncpg://conduit:conduit@postgres:5432/conduit
CONDUIT_S3_ENDPOINT_URL=http://minio:9000
```

Copy `.env.example` → `.env` (already provided with verified local values).

```
pip install -e ".[dev]"
alembic upgrade head        # once models exist
uvicorn apps.api_main:app --reload --port 8000
```

The SPA calls `http://localhost:8000/api` (absolute base), so the API is
served under `/api` with CORS enabled for the SPA origin — the conscious AD6
divergence (backend owns CORS instead of an Amplify same-origin proxy).

## Status

Scaffolding only. Every endpoint and domain/engine function raises
`NotImplementedError`; models are intentionally empty until the data model is
hardened (it is marked "subject to change"). Structure first, behaviour next.
