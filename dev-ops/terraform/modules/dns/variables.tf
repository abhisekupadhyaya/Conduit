variable "domain_name" {
  description = "Registered domain hosting the zone (prerequisite)."
  type        = string
}

variable "api_subdomain" {
  description = "Subdomain label for the backend API endpoint."
  type        = string
  default     = "api"
}

variable "eip_public_ip" {
  description = "Elastic IP the api.<domain> A record points at."
  type        = string
}
