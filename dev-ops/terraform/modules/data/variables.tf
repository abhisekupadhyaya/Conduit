variable "name_prefix" {
  type = string
}

variable "private_subnet_ids" {
  type = list(string)
}

variable "rds_security_group_id" {
  type = string
}

variable "db_name" {
  type    = string
  default = "conduit"
}

variable "db_username" {
  type    = string
  default = "conduit"
}

variable "engine_version" {
  type    = string
  default = "16"
}

variable "backup_retention_days" {
  description = "Automated backup / PITR window in days."
  type        = number
  default     = 7
}

variable "deletion_protection" {
  type    = bool
  default = true
}
