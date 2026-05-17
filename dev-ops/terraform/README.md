# dev-ops/terraform — infrastructure as code

The AWS backend deployment for Conduit. Single environment (`dev` — AD9
parameterised so additional environments are a copy, not a rewrite). Remote
state lives in a bootstrap-created S3 bucket; every non-bootstrap operation
runs as the least-privilege `ConduitTerraformOperator` role via `assume_role`.

## Layout

```
bootstrap/        Run ONCE by a human. Creates the ConduitTerraformOperator
                  role, its permissions boundary, and the S3 remote-state
                  bucket. The only step needing a directly-granted IAM policy
                  (see ../scripts/bootstrap-prereq.md).
environments/dev/ The only environment. Composes the modules; backend "s3"
                  remote state; assumes ConduitTerraformOperator.
modules/
  network/        VPC, subnets, security groups
  data/           RDS (Postgres) + object storage
  compute/        ECS service + task definitions (API; engine in-process)
  dns/            Route 53 records (zone looked up, not created)
  observability/  CloudWatch alarms / logs
  secrets/        SSM SecureString params (REPLACE_ME + ignore_changes;
                  real values written out-of-band by ../scripts/set-secrets.sh)
```

## Conventions

- **No secret values in code or state.** `*.tfvars` (except `*.tfvars.example`),
  `*.tfstate*`, and `.terraform/` are gitignored. `dev.tfvars` holds only
  references and config — copy it from `dev.tfvars.example` and fill in your
  own account ID, domain, and contact email.
- **Bootstrap is once, by a human;** everything else runs as the operator role.
- Each module pins its provider versions (`versions.tf`).

## Usage

```bash
# one-time, with the bootstrap-prereq policy attached to your IAM user
terraform -chdir=bootstrap init && terraform -chdir=bootstrap apply

# the environment, thereafter
cd environments/dev
cp dev.tfvars.example dev.tfvars   # then edit in your values
terraform init
terraform plan  -var-file=dev.tfvars
terraform apply -var-file=dev.tfvars
```

Then populate secrets and deploy with the scripts in [../scripts/](../scripts/).
Architecture rationale: [../../docs/archi/infrastructure.md](../../docs/archi/infrastructure.md).
