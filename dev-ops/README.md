# dev-ops — deployment & operations

Everything needed to stand up and operate Conduit on AWS. Project context:
[../README.md](../README.md); the *why* behind every choice here:
[../docs/archi/infrastructure.md](../docs/archi/infrastructure.md) and the
**AD-series** in [../docs/archi/decisions.md](../docs/archi/decisions.md).

One environment (`dev` — AD9 parameterised, so a second environment is a copy,
not a rewrite). One deployable: the FastAPI backend with the lifecycle engine
**in-process** (AD4) — there is no second service to deploy.

## Layout

```
terraform/   infrastructure as code (AWS)
  bootstrap/        run ONCE by a human — remote-state bucket, lock table,
                    the least-privilege ConduitTerraformOperator role
  environments/dev/ the only environment — composes the modules,
                    s3 remote state, assumes the operator role
  modules/          network · data · compute · dns · observability · secrets
scripts/     thin, idempotent Bash over the deployed stack
  deploy.sh · migrate.sh · seed.sh · set-secrets.sh · lib.sh
  bootstrap-prereq.md   the single manual IAM grant
```

Each sub-tree has its own README with the detail:
[terraform/](terraform/README.md) ·
[terraform/bootstrap/](terraform/bootstrap/README.md) ·
[terraform/environments/dev/](terraform/environments/dev/README.md) ·
[scripts/](scripts/README.md).

## Security model

- **One manual permission.** A human IAM user gets exactly enough to run
  `bootstrap` and to `sts:AssumeRole` the operator role — nothing more. Every
  later `terraform apply` and every script runs as `ConduitTerraformOperator`.
- **No secret values in code or state.** Terraform creates SSM SecureString
  params as `REPLACE_ME` with `ignore_changes`; `set-secrets.sh` is the only
  thing that writes real values, read from your environment — never a committed
  file. `*.tfvars` (except `*.tfvars.example`), `*.tfstate*`, and
  `.terraform/` are gitignored.

## Bringing up a fresh environment

```bash
# 1. one-time, with the bootstrap-prereq policy on your IAM user
terraform -chdir=terraform/bootstrap init && terraform -chdir=terraform/bootstrap apply

# 2. the environment
cd terraform/environments/dev
cp dev.tfvars.example dev.tfvars      # then fill in account ID, domain, ops email
terraform init
terraform apply -var-file=dev.tfvars

# 3. secrets, then ship
cd ../../../scripts
./set-secrets.sh dev                  # populate the SSM placeholders
./deploy.sh dev && ./migrate.sh dev && ./seed.sh dev
```

`env` defaults to `dev` everywhere (the only environment).
