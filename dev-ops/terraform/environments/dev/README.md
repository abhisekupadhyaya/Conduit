# environments/dev — the Conduit environment

The only environment (AD9: parameterised, so a second environment is a copy of
this directory, not a rewrite). This root composes the modules in
[../../modules/](../../modules/) into the full backend deployment.

- **Remote state:** S3 backend (`conduit-terraform-state`, key
  `conduit/dev/terraform.tfstate`, `us-east-1`) — created by `../../bootstrap`.
- **Identity:** every operation assumes the least-privilege
  `ConduitTerraformOperator` role created by bootstrap.

## Files

| File | Purpose |
|---|---|
| `main.tf` | Provider + S3 backend + module composition |
| `variables.tf` | Input variable declarations |
| `outputs.tf` | Outputs consumed by `../../../scripts/*` |
| `dev.tfvars.example` | Template — copy to `dev.tfvars` and fill in |
| `dev.tfvars` | **Gitignored. Never commit.** Your local values |

## Setup

```bash
cp dev.tfvars.example dev.tfvars
# edit dev.tfvars: <ACCOUNT_ID>, domain_name, api_subdomain,
# frontend_origin, ops_email — your own values
terraform init
terraform plan  -var-file=dev.tfvars
terraform apply -var-file=dev.tfvars
```

> **Why `dev.tfvars` is gitignored:** it carries account-specific references
> (account ID, owned domain, ops contact). It holds **no secret values** — real
> secrets go to SSM via `../../../scripts/set-secrets.sh`, never into tfvars or
> Terraform state — but the references still identify an account/owner, so the
> file stays local. The root `.gitignore` enforces this (`*.tfvars` is
> excluded; `*.tfvars.example` is kept).

After apply: populate SSM with `../../../scripts/set-secrets.sh dev`, then
`deploy.sh` / `migrate.sh` / `seed.sh`.
