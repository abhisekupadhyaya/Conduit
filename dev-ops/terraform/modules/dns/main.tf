# -----------------------------------------------------------------------------
# Conduit — DNS (Route 53)
#
# Hosted zone for the registered domain + an A record api.<domain> -> EIP.
# The A record is what makes the Let's Encrypt ACME challenge (and therefore
# Caddy's automatic cert) work. Domain registration and NS delegation to this
# zone are a manual prerequisite — see the name_servers output.
# -----------------------------------------------------------------------------

resource "aws_route53_zone" "this" {
  name = var.domain_name
}

resource "aws_route53_record" "api" {
  zone_id = aws_route53_zone.this.zone_id
  name    = "${var.api_subdomain}.${var.domain_name}"
  type    = "A"
  ttl     = 300
  records = [var.eip_public_ip]
}
