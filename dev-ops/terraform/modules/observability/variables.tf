variable "name_prefix" {
  type = string
}

variable "ops_email" {
  description = "Address that receives CloudWatch alarm notifications."
  type        = string
}

variable "cluster_name" {
  type = string
}

variable "service_name" {
  type = string
}

variable "db_instance_id" {
  type = string
}

variable "log_group" {
  type = string
}

variable "timer_age_threshold_seconds" {
  description = "Alarm if the oldest unfired timer exceeds this age."
  type        = number
  default     = 120
}
