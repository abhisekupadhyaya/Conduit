variable "name_prefix" {
  type = string
}

variable "env" {
  type = string
}

variable "public_subnet_id" {
  type = string
}

variable "ec2_security_group_id" {
  type = string
}

variable "eip_allocation_id" {
  type = string
}

variable "permissions_boundary_arn" {
  description = "ConduitPermissionsBoundary — applied to every role this module creates."
  type        = string
}

variable "api_fqdn" {
  description = "api.<domain> — the host Caddy obtains a cert for and proxies."
  type        = string
}

variable "acme_email" {
  description = "Optional contact email for Let's Encrypt. Empty = anonymous."
  type        = string
  default     = ""
}

variable "frontend_origin" {
  description = "Operator-owned Amplify SPA origin — written into CONDUIT_CORS_ORIGINS (AD6 divergence: backend owns CORS)."
  type        = string
}

variable "secret_parameter_arns" {
  description = "SSM SecureString ARNs the execution role may read."
  type        = list(string)
}

variable "secret_names" {
  description = "Logical-name -> SSM parameter-name map for task-def secret injection."
  type        = map(string)
}

variable "instance_type" {
  type    = string
  default = "t4g.small"
}

variable "host_port" {
  description = "Static host port the API task binds; Caddy proxies localhost:<port>."
  type        = number
  default     = 8000
}

variable "task_cpu" {
  type    = number
  default = 1024
}

variable "task_memory" {
  type    = number
  default = 1536
}

variable "image_tag" {
  description = "ECR image tag the task definitions run."
  type        = string
  default     = "latest"
}

variable "desired_count" {
  description = "ECS service desired count. 0 on first apply (no image yet); scripts/deploy.sh bumps to 1."
  type        = number
  default     = 0
}

variable "openai_model" {
  type    = string
  default = "gpt-5.4-mini"
}
