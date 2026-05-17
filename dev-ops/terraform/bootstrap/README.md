# Bootstrap — Terraform state backend & operator role

Run this **once**, before `environments/dev`. It solves the chicken-and-egg
problem (the remote backend cannot store the state that creates the remote
backend) and establishes the "one permission" security model.

## What it creates

| Resource | Name |
|---|---|
| KMS key | `alias/conduit-terraform-state` |
| S3 bucket (state) | `conduit-terraform-state` — versioned, TLS-only, no public access |
| DynamoDB table (lock) | `conduit-terraform-lock` |
| Permissions boundary | `ConduitPermissionsBoundary` |
| Operator IAM role | `ConduitTerraformOperator` |

## Prerequisite — the only manual grant

Attach a policy to your IAM user allowing it to (a) create the resources
above and (b) `sts:AssumeRole` on `ConduitTerraformOperator`. See
`../../scripts/bootstrap-prereq.md` for the exact JSON. Nothing else is granted
to the human user — every later `terraform apply` runs as the operator role.

## Run

```bash
cd dev-ops/terraform/bootstrap
terraform init        # local state — intentional
terraform apply
```

Copy the `terraform_operator_role_arn` output into
`../environments/dev/dev.tfvars` (`terraform_role_arn`).

## State

This config uses **local state** (`terraform.tfstate`, git-ignored). It rarely
changes. If lost, re-import the resources rather than recreating them:

```bash
terraform import aws_s3_bucket.terraform_state conduit-terraform-state
terraform import aws_dynamodb_table.terraform_lock conduit-terraform-lock
terraform import aws_iam_role.terraform_operator ConduitTerraformOperator
terraform import aws_iam_policy.permissions_boundary \
  arn:aws:iam::<ACCOUNT_ID>:policy/ConduitPermissionsBoundary
```

## Teardown

Only when permanently destroying all Conduit infrastructure: destroy
`environments/dev` first, empty the state bucket, then `terraform destroy`
here.
