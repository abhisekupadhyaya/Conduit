output "state_bucket_name" {
  description = "S3 bucket for Terraform remote state (set in environments/dev backend)."
  value       = aws_s3_bucket.terraform_state.id
}

output "lock_table_name" {
  description = "DynamoDB table for Terraform state locking."
  value       = aws_dynamodb_table.terraform_lock.name
}

output "kms_key_alias" {
  description = "KMS alias that encrypts remote state."
  value       = aws_kms_alias.terraform_state.name
}

output "terraform_operator_role_arn" {
  description = "Role every later `terraform apply` assumes. Copy into environments/dev/dev.tfvars."
  value       = aws_iam_role.terraform_operator.arn
}

output "permissions_boundary_arn" {
  description = "Permissions ceiling applied to the operator role."
  value       = aws_iam_policy.permissions_boundary.arn
}
