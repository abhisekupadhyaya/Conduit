output "api_fqdn" {
  value = aws_route53_record.api.name
}

output "zone_id" {
  value = aws_route53_zone.this.zone_id
}

output "name_servers" {
  description = "Delegate the registered domain to these NS records (manual, one-time)."
  value       = aws_route53_zone.this.name_servers
}
