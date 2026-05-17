# -----------------------------------------------------------------------------
# Conduit — Secrets (SSM Parameter Store SecureString, NOT Secrets Manager)
#
# Parameter Store standard tier is free; this is the deliberate Conduit cost
# divergence from the GPTree pattern. Two classes of secret:
#
#   Terraform-owned   (database_url, jwt_secret) — TF knows the value; written
#                      directly. Lands in the KMS-encrypted remote state.
#   Operator-supplied (openai_api_key, seed creds) — seeded as a placeholder
#                      with ignore_changes; real values written post-apply by
#                      scripts/set-secrets.sh so they never enter state.
# -----------------------------------------------------------------------------

resource "random_password" "jwt" {
  length  = 48
  special = false
}

locals {
  prefix = "/conduit/${var.env}"
}

# --- Terraform-owned ------------------------------------------------------

resource "aws_ssm_parameter" "database_url" {
  name        = "${local.prefix}/CONDUIT_DATABASE_URL"
  description = "Conduit ${var.env} database URL (asyncpg)."
  type        = "SecureString"
  value       = var.database_url
  tags        = { Project = "conduit" }
}

resource "aws_ssm_parameter" "jwt_secret" {
  name        = "${local.prefix}/CONDUIT_JWT_SECRET"
  description = "Conduit ${var.env} JWT signing secret."
  type        = "SecureString"
  value       = random_password.jwt.result
  tags        = { Project = "conduit" }
}

# --- Operator-supplied (placeholder + ignore_changes) ---------------------

resource "aws_ssm_parameter" "openai_api_key" {
  name        = "${local.prefix}/CONDUIT_OPENAI_API_KEY"
  description = "Conduit ${var.env} OpenAI API key — set via scripts/set-secrets.sh."
  type        = "SecureString"
  value       = "REPLACE_ME"
  tags        = { Project = "conduit" }
  lifecycle {
    ignore_changes = [value]
  }
}

resource "aws_ssm_parameter" "seed_supervisor_username" {
  name        = "${local.prefix}/CONDUIT_SEED_SUPERVISOR_USERNAME"
  description = "Conduit ${var.env} bootstrap supervisor username — set via scripts/set-secrets.sh."
  type        = "SecureString"
  value       = "REPLACE_ME"
  tags        = { Project = "conduit" }
  lifecycle {
    ignore_changes = [value]
  }
}

resource "aws_ssm_parameter" "seed_supervisor_password" {
  name        = "${local.prefix}/CONDUIT_SEED_SUPERVISOR_PASSWORD"
  description = "Conduit ${var.env} bootstrap supervisor password — set via scripts/set-secrets.sh."
  type        = "SecureString"
  value       = "REPLACE_ME"
  tags        = { Project = "conduit" }
  lifecycle {
    ignore_changes = [value]
  }
}
