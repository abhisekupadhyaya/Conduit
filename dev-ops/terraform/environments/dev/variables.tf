variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "env" {
  type    = string
  default = "dev"
}

variable "terraform_role_arn" {
  description = "ConduitTerraformOperator ARN from `bootstrap` output."
  type        = string
}

variable "permissions_boundary_arn" {
  description = "ConduitPermissionsBoundary ARN from `bootstrap` output — applied to roles created here."
  type        = string
}

variable "domain_name" {
  description = "Registered domain (prerequisite). Hosted zone is created here; delegate NS to it."
  type        = string
}

variable "api_subdomain" {
  type    = string
  default = "api"
}

variable "frontend_origin" {
  description = "Operator-owned Amplify SPA origin, e.g. https://app.example.com — written to CONDUIT_CORS_ORIGINS."
  type        = string
}

variable "acme_email" {
  description = "Optional Let's Encrypt contact email."
  type        = string
  default     = ""
}

variable "ops_email" {
  description = "Address subscribed to the CloudWatch alarm SNS topic (confirm the subscription email)."
  type        = string
}

variable "image_tag" {
  description = "ECR image tag the task definitions run. scripts/deploy.sh pushes and updates this."
  type        = string
  default     = "latest"
}

variable "vpc_cidr" {
  type    = string
  default = "10.0.0.0/16"
}

variable "db_backup_retention_days" {
  type    = number
  default = 7
}

variable "db_deletion_protection" {
  type    = bool
  default = true
}
