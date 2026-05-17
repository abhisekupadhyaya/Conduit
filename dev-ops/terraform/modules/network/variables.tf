variable "name_prefix" {
  description = "Resource name prefix, e.g. conduit-dev."
  type        = string
}

variable "vpc_cidr" {
  description = "VPC CIDR block."
  type        = string
  default     = "10.0.0.0/16"
}
