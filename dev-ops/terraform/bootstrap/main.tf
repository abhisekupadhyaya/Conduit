# -----------------------------------------------------------------------------
# Conduit — Terraform State Backend (Bootstrap)
#
# Standalone config, LOCAL state, run ONCE before everything else. Creates the
# chicken-and-egg prerequisites the main environment needs:
#   - KMS key that encrypts remote state at rest
#   - S3 bucket for remote state (versioned, TLS-only, no public access)
#   - DynamoDB table for state locking (the only DynamoDB anywhere — IaC plumbing)
#   - ConduitPermissionsBoundary + ConduitTerraformOperator (least-privilege role
#     every later `terraform apply` assumes)
#
# See README.md for the run procedure.
# -----------------------------------------------------------------------------

terraform {
  required_version = ">= 1.5"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # Local state on purpose: the remote backend does not exist yet.
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project   = "conduit"
      ManagedBy = "terraform-bootstrap"
    }
  }
}

data "aws_caller_identity" "current" {}

# ---------------------------------------------------------------------------
# KMS key — encrypts Terraform state at rest
# ---------------------------------------------------------------------------

resource "aws_kms_key" "terraform_state" {
  description             = "Encrypts Conduit Terraform state in S3"
  deletion_window_in_days = 30
  enable_key_rotation     = true
}

resource "aws_kms_alias" "terraform_state" {
  name          = "alias/conduit-terraform-state"
  target_key_id = aws_kms_key.terraform_state.key_id
}

# ---------------------------------------------------------------------------
# S3 bucket — Terraform remote state
# ---------------------------------------------------------------------------

resource "aws_s3_bucket" "terraform_state" {
  bucket = var.state_bucket_name

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_s3_bucket_versioning" "terraform_state" {
  bucket = aws_s3_bucket.terraform_state.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "terraform_state" {
  bucket = aws_s3_bucket.terraform_state.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.terraform_state.arn
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_policy" "terraform_state_ssl" {
  bucket = aws_s3_bucket.terraform_state.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "DenyNonSSL"
      Effect    = "Deny"
      Principal = "*"
      Action    = "s3:*"
      Resource = [
        aws_s3_bucket.terraform_state.arn,
        "${aws_s3_bucket.terraform_state.arn}/*"
      ]
      Condition = { Bool = { "aws:SecureTransport" = "false" } }
    }]
  })
}

resource "aws_s3_bucket_public_access_block" "terraform_state" {
  bucket                  = aws_s3_bucket.terraform_state.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# ---------------------------------------------------------------------------
# DynamoDB — state lock table
# ---------------------------------------------------------------------------

resource "aws_dynamodb_table" "terraform_lock" {
  name         = var.lock_table_name
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "LockID"

  attribute {
    name = "LockID"
    type = "S"
  }
}
