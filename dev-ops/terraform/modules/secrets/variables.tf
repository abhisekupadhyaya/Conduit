variable "env" {
  description = "Environment name — the SSM path segment, e.g. dev."
  type        = string
}

variable "database_url" {
  description = "Terraform-composed CONDUIT_DATABASE_URL."
  type        = string
  sensitive   = true
}
