variable "name_prefix" {
  type = string
}

variable "env" {
  type = string
}

variable "vpc_id" {
  type = string
}

variable "public_subnet_ids" {
  description = "Public subnets for the ALB and the Fargate tasks (egress via IGW, no NAT)."
  type        = list(string)
}

variable "alb_security_group_id" {
  type = string
}

variable "task_security_group_id" {
  type = string
}

variable "certificate_arn" {
  description = "Validated ACM cert ARN for the API FQDN (from the dns module)."
  type        = string
}

variable "zone_id" {
  description = "Existing Route 53 zone id (from the dns module) for the ALB A-alias."
  type        = string
}

variable "api_fqdn" {
  description = "Fully-qualified API hostname, e.g. api.conduit.narv.ai."
  type        = string
}

variable "frontend_origin" {
  description = "Operator-owned SPA origin -> CONDUIT_CORS_ORIGINS (backend owns CORS, AD6)."
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

variable "permissions_boundary_arn" {
  type = string
}

variable "container_port" {
  type    = number
  default = 8000
}

variable "image_tag" {
  type    = string
  default = "latest"
}

variable "desired_count" {
  description = "ECS service desired count. 0 on first apply (no image yet); deploy.sh bumps to 1."
  type        = number
  default     = 0
}

variable "api_cpu" {
  description = "Fargate CPU units for the API task (valid Fargate combo with api_memory)."
  type        = number
  default     = 512
}

variable "api_memory" {
  type    = number
  default = 1024
}

variable "oneoff_cpu" {
  description = "Smaller reservation for one-off migrate/seed tasks."
  type        = number
  default     = 256
}

variable "oneoff_memory" {
  type    = number
  default = 512
}

variable "openai_model" {
  type    = string
  default = "gpt-5.4-mini"
}
