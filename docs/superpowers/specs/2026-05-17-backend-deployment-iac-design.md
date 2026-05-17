# Backend Deployment IaC — Design

**Date:** 2026-05-17
**Status:** Approved, implementing
**Scope:** Terraform + scripts that deploy the Conduit **backend**. Frontend
(Amplify) is owned by the operator and explicitly out of scope here.

## Goal

Turn the converged architecture (`docs/archi/`) into runnable infrastructure
for the backend, with a completeness guarantee: every backend runtime
requirement is either provisioned, scripted, or an explicitly documented
deferral. Nothing silently missing.

## Constraints (from `docs/archi/`)

- AD1: ECS on **EC2** (`t4g.small`), not Fargate.
- AD2: **No load balancer**; Caddy on the host terminates TLS; **Elastic IP**
  is the stable address.
- AD3: managed **RDS Postgres `t4g.micro` single-AZ + PITR**, `sslmode=require`.
- AD4/AD5: engine runs **in-process** in the API container; DB-backed timers.
- AD6 divergence: backend owns CORS (the SPA calls an absolute `/api` base).
- Secrets in **SSM Parameter Store SecureString** (free) — *not* Secrets
  Manager (deliberate cost decision; this is where the GPTree pattern is
  adapted rather than copied).
- AD9: single environment, parameterised.
- No NAT — egress via the Internet Gateway.

## Completeness audit (backend runtime contract → resolution)

| Backend need | Resolution |
|---|---|
| Container image (`uvicorn apps.api_main:app`) | **`backend/Dockerfile`** (authored here) |
| Postgres, `sslmode=require` | `modules/data` (RDS) |
| `alembic upgrade head` | `modules/compute` migration task def + `scripts/migrate.sh` |
| Bootstrap supervisor (`python -m conduit.seed`) | `modules/compute` seed task def + `scripts/seed.sh` |
| JWT secret, OpenAI key, DB URL, seed creds | `modules/secrets` (SSM SecureString) |
| Object storage (`boto3`, `CONDUIT_S3_*`) | **Deferred** — backend is stubs; documented in `infrastructure.md`. Additive when behaviour lands. |
| CORS origin = Amplify URL | `frontend_origin` Terraform input variable (operator-supplied) |
| TLS / EIP / network / observability | `network` / `compute` / `dns` / `observability` |

## Structure

```
dev-ops/
├── terraform/
│   ├── bootstrap/        local state, run once: KMS, S3 state bucket,
│   │                     DynamoDB lock, ConduitPermissionsBoundary,
│   │                     ConduitTerraformOperator role
│   ├── modules/
│   │   ├── network/      VPC, public + 2 private subnets, SGs, EIP, IGW
│   │   ├── data/         RDS t4g.micro single-AZ + PITR
│   │   ├── secrets/      SSM SecureString (placeholder + ignore_changes)
│   │   ├── compute/      ECS cluster, ECR, EC2 launch template + Caddy,
│   │   │                 API/migrate/seed task defs, service
│   │   ├── dns/          Route53 zone + A api.<domain> → EIP
│   │   └── observability/ CloudWatch logs/alarms, SNS, timer-age metric
│   └── environments/dev/ only env: S3 backend + assume_role; composes
│                          modules; input frontend_origin → CORS
└── scripts/  bootstrap-prereq.md · deploy.sh · migrate.sh · seed.sh ·
              set-secrets.sh
```

## Security model ("one permission → the rest self-provisions")

1. Operator attaches the bootstrap policy to their IAM user (only manual grant).
2. `terraform -chdir=bootstrap apply` (local state) → state backend + scoped
   `ConduitTerraformOperator` role under `ConduitPermissionsBoundary`.
3. `terraform -chdir=environments/dev apply` assumes the operator role →
   all backend infra; ECS service starts at `desired_count = 0`.
4. `set-secrets.sh` writes real SSM values; `deploy.sh` builds/pushes the
   image and bumps `desired_count` to 1; `migrate.sh` then `seed.sh` run the
   one-off ECS tasks. `outputs.tf` prints every command copy-paste ready.

## Deliberate deferrals

- **Application object storage (S3).** Backend behaviour is stubbed; no code
  path exercises `CONDUIT_S3_*` in v1. Recorded in `infrastructure.md`.
  Re-introducing it is an additive bucket + task-role policy change.

## Doc reconciliation

- `code-structure.md`: flat `terraform/` layout → `modules/` + `environments/`;
  add `seed.sh`.
- `infrastructure.md`: add the operator-role / permissions-boundary resource
  row; add the object-storage deferral note.
</content>
</invoke>
