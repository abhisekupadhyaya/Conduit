# Code Structure

A vertical-slice-per-portal layout, 4-layer internals
(`api / services / dal / schemas`), with the AD10 simplifications applied (no
multi-tenancy, no RBAC, one deployable, engine in-process). The four portal
slices (guest/servicer/supervisor/public) are the **only** places with
`api/services/dal/schemas`; `engine/` lives under `shared/`; triage is shared
**domain** logic, not a slice. *This reflects the realized scaffold.*

```
Conduit/
├── README.md
├── Makefile
├── docs/
│   └── archi/                        # these documents
│
├── backend/
│   ├── pyproject.toml                # PEP 621, ruff, mypy
│   ├── alembic.ini
│   ├── .env.example                  # Postgres/MinIO/OpenAI/JWT (local-verified)
│   ├── apps/
│   │   └── api_main.py               # → conduit.main:app  (single deployable; engine in-process)
│   ├── conduit/
│   │   ├── main.py                   # FastAPI app: composes 4 slices, in-process engine lifespan
│   │   ├── core/
│   │   │   ├── config.py             # typed settings (env CONDUIT_*)
│   │   │   ├── deps.py               # DI: db session, current actor, role gates (NO rbac)
│   │   │   ├── security.py           # app-managed JWT (AD8)
│   │   │   ├── middleware.py         # CORS (AD6 divergence) + request id
│   │   │   └── exceptions.py
│   │   ├── guest/                    # ── the ONLY slices ──
│   │   │   └── api/ services/ dal/ schemas/   # FR-24 (conversation)
│   │   ├── servicer/
│   │   │   └── api/ services/ dal/ schemas/   # queue + task actions
│   │   ├── supervisor/
│   │   │   └── api/ services/ dal/ schemas/   # FR-25 (decisions, setup, …)
│   │   ├── public/
│   │   │   └── api/ services/ dal/ schemas/   # login + health
│   │   └── shared/                   # cross-portal — NOT a slice
│   │       ├── db.py                 # async engine/session + Base
│   │       ├── models/               # ORM entities (empty until data model hardens)
│   │       ├── events/               # append-only event log (the spine)
│   │       ├── domain/               # triage · routing · lifecycle  (triage lives HERE)
│   │       ├── engine/               # runner · timers · spine · sweeper  (in shared/, AD4/AD5)
│   │       └── integrations/         # openai (AD11) · storage (S3/MinIO)
│   ├── migrations/                   # Alembic (env.py: url+metadata from settings)
│   │   └── versions/
│   ├── seed/
│   └── tests/                        # api · domain · engine · smoke
│
├── frontend/
│   ├── package.json  vite.config.ts  index.html
│   ├── .env  .env.example            # VITE_API_BASE (absolute, env-driven)
│   └── src/
│       ├── main.tsx                  # ThemeProvider → Router → Auth → Tooltip
│       ├── App.tsx                   # role-routed; one shared shell per route
│       ├── auth/                     # use-auth, auth-provider, require-auth, login-form/page
│       ├── lib/                      # api-client, query-client (TanStack), role-routing, utils
│       ├── public/                   # landing (auth-aware redirect)
│       ├── hooks/                    # shared (use-mobile)
│       ├── components/
│       │   ├── ui/                   # shadcn primitives
│       │   ├── theme-provider.tsx    # light/dark/system
│       │   └── layout/               # SHARED shell: app-shell, app-sidebar, nav-main, nav-user, app-brand
│       └── shell/
│           ├── guest/                # nav.tsx (the only per-portal diff) + index.tsx + hooks/
│           ├── servicer/             # nav.tsx + index.tsx + hooks/
│           └── supervisor/           # nav.tsx + index.tsx + hooks/   (hooks/ = TanStack Query)
│
└── dev-ops/
    ├── terraform/                    # single env (dev); modules parameterised for future envs (AD9)
    │   ├── bootstrap/                # LOCAL state, run once: KMS + S3 state
    │   │                             #   bucket + DynamoDB lock + permissions
    │   │                             #   boundary + ConduitTerraformOperator role
    │   ├── modules/
    │   │   ├── network/              # VPC, public + 2 private subnets, SGs, EIP
    │   │   ├── compute/              # ECS cluster, ECR, EC2 + Caddy (user-data),
    │   │   │                         #   API/migrate/seed task defs, service
    │   │   ├── data/                 # RDS t4g.micro single-AZ + PITR
    │   │   ├── dns/                  # Route53 zone + A api.<domain> → EIP
    │   │   ├── secrets/              # SSM SecureString (OpenAI key, DB URL, JWT)
    │   │   └── observability/        # CloudWatch alarms, SNS, timer-age metric
    │   └── environments/
    │       └── dev/                  # only env: S3 backend + assume_role;
    │                                 #   composes modules; frontend_origin in
    │                                 #   (Amplify is operator-owned, not in TF)
    └── scripts/                      # standard build/deploy ops, AWS-targeted
        ├── deploy.sh                 # ECR build/push + roll service (count 0→1)
        ├── migrate.sh                # one-off ECS task: alembic upgrade head
        ├── seed.sh                   # one-off ECS task: python -m conduit.seed
        └── set-secrets.sh            # write operator secrets to SSM post-apply
```

## Deltas from a conventional multi-portal template

- **No** `super_admin`/multi-tenant slice, **no** `core/rbac.py`, **no**
  `{tenant_slug}` route prefix (AD10).
- **No `triage/` slice.** Triage is shared *domain* logic
  (`shared/domain/triage.py`), triggered from `guest/services/intake.py`.
  `api/services/dal/schemas` exist **only** under the four portals.
- **`engine/` lives under `shared/`** (`shared/engine/`), not at package root —
  it is cross-portal runtime machinery alongside `db`, `models`, `events`.
- **One** backend deployable — the engine is in-process, not a second
  async-worker service (AD4); it is the riskiest surface, most heavily tested.
- **Frontend uses one shared shell** (`components/layout/`); the only
  per-portal difference is `shell/<portal>/nav.tsx`.
- **All frontend API access goes through TanStack Query** — `useQuery`
  (live surfaces poll, per AD7) / `useMutation`, in `shell/<portal>/hooks/`,
  over `lib/api-client`. The **only** exception is auth (login/logout), which
  stays a direct call in `auth/auth-provider`.
- Env-driven config both sides: backend `CONDUIT_*`, frontend `VITE_API_BASE`
  (absolute base → backend owns CORS, the conscious AD6 divergence). Local dev
  uses the docker-compose Postgres/MinIO as the RDS/S3 alternatives.
- `dev-ops/{terraform,scripts}` + Amplify is the AWS deploy target. Two
  independent pipelines: frontend = Amplify git push; backend = ECR → ECS.
- **Account persistence is owned by `public/dal/accounts.py`** and imported by
  `supervisor` services (one-directional public←supervisor) — single source of
  truth for the one IDENTITY table; no DAL duplicated across slices.
