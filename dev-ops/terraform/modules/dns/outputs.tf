output "api_fqdn" {
  value = local.fqdn
}

output "zone_id" {
  description = "Existing hosted zone id — compute creates the ALB A-alias here."
  value       = data.aws_route53_zone.this.zone_id
}

output "certificate_arn" {
  description = "Validated ACM cert for the API FQDN (consumed by the ALB HTTPS listener)."
  value       = aws_acm_certificate_validation.api.certificate_arn
}
