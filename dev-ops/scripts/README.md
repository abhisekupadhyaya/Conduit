# dev-ops/scripts — operational scripts

Thin, idempotent Bash wrappers around the deployed AWS stack. They assume the
Terraform in [../terraform/](../terraform/) has been applied and that you can
assume the `ConduitTerraformOperator` role (or have equivalent access). All
scripts are `set -euo pipefail` and resolve config from Terraform outputs /
the environment — they hold **no secret values**.

| Script | What it does | Usage |
|---|---|---|
| `deploy.sh` | Build the backend image, push to ECR, roll the ECS service | `deploy.sh [env] [tag]` |
| `migrate.sh` | Run DB migrations as a one-off ECS task (`alembic upgrade head`) | `migrate.sh [env]` |
| `seed.sh` | Seed the bootstrap supervisor as a one-off ECS task (idempotent — upserts) | `seed.sh [env]` |
| `set-secrets.sh` | Write operator-supplied secret **values** into SSM SecureString params | `set-secrets.sh [env]` |
| `lib.sh` | Shared helpers — **sourced, not executed** | — |

`env` defaults to `dev` (the only environment — AD9 parameterised).

## Secrets model

Terraform creates the SSM SecureString parameters with a `REPLACE_ME`
placeholder and `ignore_changes` on the value, so **real secrets never enter
Terraform state**. `set-secrets.sh` is the only thing that writes the real
values, and it reads them from your environment / prompts — never from a
committed file. See [bootstrap-prereq.md](bootstrap-prereq.md) for the single
manual IAM grant required before any of this runs.

## Order on a fresh environment

1. `terraform -chdir=../terraform/bootstrap apply` (one-time, see bootstrap-prereq.md)
2. `terraform -chdir=../terraform/environments/dev apply`
3. `set-secrets.sh dev` — populate the SSM placeholders
4. `deploy.sh dev` → `migrate.sh dev` → `seed.sh dev`
