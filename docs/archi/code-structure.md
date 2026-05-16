# Code Structure

A vertical-slice-per-portal layout, 4-layer internals
(`api / services / dal / schemas`), with the AD10 simplifications applied (no
multi-tenancy, no RBAC, one deployable, engine in-process).

```
Conduit/
├── README.md
├── Makefile
├── docs/
│   └── archi/                        # these documents
│
├── backend/
│   ├── pyproject.toml                # Poetry, ruff, mypy
│   ├── apps/
│   │   └── api_main.py               # → conduit.main:app  (single deployable; engine in-process)
│   ├── conduit/
│   │   ├── main.py                   # FastAPI app: composes portal routers, starts engine task
│   │   ├── core/
│   │   │   ├── deps.py               # DI: db session, current actor, role gates (NO rbac.py)
│   │   │   ├── security.py           # app-managed JWT (guest/servicer/supervisor)
│   │   │   ├── middleware.py
│   │   │   └── exceptions.py
│   │   ├── guest/                    # portal slice — FR-24 (one conversation screen)
│   │   │   ├── api/                  #   routers, one file/resource; __init__ composes
│   │   │   ├── services/             #   use-cases, verb-named
│   │   │   ├── dal/                  #   the ONLY place that touches the DB
│   │   │   └── schemas/              #   Pydantic in/out
│   │   ├── servicer/                 # same 4-layer shape
│   │   │   └── api/ services/ dal/ schemas/
│   │   ├── supervisor/               # the big one — FR-25 (8 pages)
│   │   │   └── api/ services/ dal/ schemas/
│   │   ├── public/                   # login, health
│   │   │   └── api/ services/ dal/ schemas/
│   │   ├── triage/                   # mechanical rulebook, decompose, issue-code classify
│   │   │   └── services/ dal/ schemas/
│   │   ├── engine/                   # lifecycle core (in-process background task)
│   │   │   ├── runner.py             #   poll loop (FOR UPDATE SKIP LOCKED)
│   │   │   ├── timers.py             #   dual timers, supervisor-SLA, bounded backstop
│   │   │   ├── spine.py              #   stall detection → escalation → auto-proceed
│   │   │   ├── sweeper.py            #   reconciliation watchdog
│   │   │   └── services/ dal/
│   │   └── shared/
│   │       ├── db.py                 # async engine/session
│   │       ├── models/               # SQLAlchemy domain models
│   │       ├── events/               # append-only event log (awareness + analytics)
│   │       └── integrations/
│   │           └── openai.py         # client + circuit-breaker (AD11)
│   ├── migrations/                   # Alembic
│   │   └── versions/
│   ├── seed/                         # default issue-code catalog, SLA presets
│   └── tests/                        # mirrors the tree
│       ├── api/{guest,servicer,supervisor,public}/
│       ├── service/{guest,servicer,supervisor,triage}/
│       ├── engine/                   # timers/spine/sweeper — heaviest tested
│       ├── integration/
│       ├── concurrency/              # SKIP LOCKED double-fire safety
│       └── smoke/
│
├── frontend/
│   ├── package.json
│   ├── vite.config.ts
│   ├── index.html
│   └── src/
│       ├── main.tsx
│       ├── App.tsx                   # role-routed to the right shell
│       ├── auth/                     # AuthProvider, LoginPage, RequireAuth, hooks
│       ├── lib/                      # api-client, query-client, role-routing, format
│       ├── components/
│       │   ├── ui/                   # design system
│       │   └── …                     # shared cross-portal components
│       ├── hooks/                    # shared hooks
│       ├── public/                   # public pages
│       └── shell/
│           ├── guest/                # one conversation screen + login
│           │   └── layout/ components/ hooks/
│           ├── servicer/             # queue + task detail
│           │   └── layout/ components/ hooks/
│           └── supervisor/           # 8 pages: awareness, decision queue, setup, KB, …
│               └── layout/ components/ hooks/
│
└── dev-ops/
    ├── terraform/                    # single env, parameterised for future envs (AD9)
    │   ├── main.tf  variables.tf  outputs.tf
    │   ├── network.tf                # VPC, public subnet, SG, EIP
    │   ├── compute.tf                # ECS cluster, EC2 container instance, task def, service
    │   ├── data.tf                   # RDS t4g.micro single-AZ + PITR
    │   ├── edge.tf                   # Amplify app, /api/* reverse-proxy, custom domain
    │   ├── secrets.tf                # SSM SecureString (OpenAI key, DB creds, JWT secret)
    │   └── observability.tf          # CloudWatch logs/alarms, SNS
    └── scripts/                      # standard build/deploy ops, AWS-targeted
        ├── build.sh  push.sh  deploy.sh
        ├── migrate.sh                # one-off ECS task: alembic upgrade
        └── secrets.sh  smoke.sh
```

## Deltas from a conventional multi-portal template

- **No** `super_admin`/multi-tenant slice, **no** `core/rbac.py`, **no**
  `{tenant_slug}` route prefix (AD10).
- **One** backend deployable — the engine is in-process, not a second
  async-worker service (AD4).
- `engine/` is a net-new package with no analogue in the usual template; it is
  the riskiest surface and the most heavily tested (`tests/engine/`,
  `tests/concurrency/`).
- `dev-ops/{terraform,scripts}` + Amplify is the AWS deploy target.
- Two independent deploy pipelines: frontend = Amplify git push; backend =
  ECR → ECS rolling update.
