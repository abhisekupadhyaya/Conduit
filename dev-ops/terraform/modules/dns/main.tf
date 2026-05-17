# -----------------------------------------------------------------------------
# Conduit — DNS + ACM (Route 53 zone already exists for narv.ai)
#
# Looks up the existing hosted zone and provisions an ACM certificate for
# api.<sub>.<zone>, validated automatically via DNS records in that zone.
# AWS renews the cert; no Caddy, no Let's Encrypt, no host TLS plumbing.
#
# The A-alias (api.<sub>.<zone> -> ALB) is created in the compute module,
# which owns the ALB — so this module has no dependency on compute.
# -----------------------------------------------------------------------------

data "aws_route53_zone" "this" {
  name         = var.domain_name
  private_zone = false
}

locals {
  fqdn = "${var.api_subdomain}.${var.domain_name}"
}

resource "aws_acm_certificate" "api" {
  domain_name       = local.fqdn
  validation_method = "DNS"

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_route53_record" "acm_validation" {
  for_each = {
    for dvo in aws_acm_certificate.api.domain_validation_options :
    dvo.domain_name => {
      name   = dvo.resource_record_name
      type   = dvo.resource_record_type
      record = dvo.resource_record_value
    }
  }

  zone_id = data.aws_route53_zone.this.zone_id
  name    = each.value.name
  type    = each.value.type
  ttl     = 60
  records = [each.value.record]

  allow_overwrite = true
}

resource "aws_acm_certificate_validation" "api" {
  certificate_arn         = aws_acm_certificate.api.arn
  validation_record_fqdns = [for r in aws_route53_record.acm_validation : r.fqdn]
}
