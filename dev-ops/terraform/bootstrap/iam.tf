# -----------------------------------------------------------------------------
# Conduit — Terraform operator role + permissions boundary
#
# The "one permission" model: an operator attaches only the bootstrap policy to
# their IAM user. Bootstrap then provisions a scoped ConduitTerraformOperator
# role (capped by ConduitPermissionsBoundary) that every later `terraform
# apply` assumes — the user never holds broad infrastructure permissions.
# -----------------------------------------------------------------------------

resource "aws_iam_policy" "permissions_boundary" {
  name        = "ConduitPermissionsBoundary"
  description = "Permissions ceiling for the Conduit Terraform operator — prevents privilege escalation."

  policy = templatefile("${path.module}/policies/permissions-boundary.json", {
    account_id  = data.aws_caller_identity.current.account_id
    aws_region  = var.aws_region
    kms_key_arn = aws_kms_key.terraform_state.arn
  })
}

resource "aws_iam_role" "terraform_operator" {
  name                 = "ConduitTerraformOperator"
  max_session_duration = 3600
  permissions_boundary = aws_iam_policy.permissions_boundary.arn

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { AWS = data.aws_caller_identity.current.arn }
      Action    = "sts:AssumeRole"
    }]
  })

  tags = { Name = "ConduitTerraformOperator" }
}

resource "aws_iam_role_policy" "terraform_operator" {
  name = "ConduitTerraformOperatorPolicy"
  role = aws_iam_role.terraform_operator.id

  policy = templatefile("${path.module}/policies/terraform-operator-policy.json", {
    account_id   = data.aws_caller_identity.current.account_id
    aws_region   = var.aws_region
    state_bucket = aws_s3_bucket.terraform_state.arn
    kms_key_arn  = aws_kms_key.terraform_state.arn
    boundary_arn = aws_iam_policy.permissions_boundary.arn
  })
}
