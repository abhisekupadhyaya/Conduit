output "api_fqdn" {
  description = "Backend endpoint Caddy serves over TLS."
  value       = module.dns.api_fqdn
}

output "name_servers" {
  description = "Delegate the registered domain to these (manual, one-time)."
  value       = module.dns.name_servers
}

output "eip_public_ip" {
  value = module.network.eip_public_ip
}

output "ecr_repository_url" {
  value = module.compute.ecr_repository_url
}

# --- Ready-to-run helper commands -----------------------------------------
# Mirrors the "one command takes care of the rest" UX. Fill <REGION> from
# aws_region if you did not configure a default profile region.

output "next_steps" {
  description = "Run these in order after `terraform apply`."
  value = {
    "1_set_secrets" = "dev-ops/scripts/set-secrets.sh ${var.env}"
    "2_deploy"      = "dev-ops/scripts/deploy.sh ${var.env}"
    "3_migrate"     = "dev-ops/scripts/migrate.sh ${var.env}"
    "4_seed"        = "dev-ops/scripts/seed.sh ${var.env}"
  }
}

output "deploy_context" {
  description = "Values the scripts consume."
  value = {
    region          = var.aws_region
    cluster         = module.compute.cluster_name
    service         = module.compute.service_name
    ecr_repo        = module.compute.ecr_repository_url
    api_task        = module.compute.api_task_family
    migrate_task    = module.compute.migrate_task_family
    seed_task       = module.compute.seed_task_family
    ssm_path_prefix = module.secrets.path_prefix
    log_group       = module.compute.log_group
  }
}
