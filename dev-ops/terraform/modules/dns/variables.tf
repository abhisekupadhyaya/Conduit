variable "domain_name" {
  description = "Existing Route 53 hosted zone (e.g. narv.ai)."
  type        = string
}

variable "api_subdomain" {
  description = "Subdomain prefix for the backend API endpoint (e.g. api.conduit)."
  type        = string
  default     = "api"
}
