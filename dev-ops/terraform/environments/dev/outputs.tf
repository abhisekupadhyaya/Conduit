output "api_fqdn" {
  description = "Backend endpoint, served over TLS by the ALB (ACM cert)."
  value       = "https://${module.dns.api_fqdn}"
}

output "alb_dns_name" {
  description = "ALB DNS name (the api.<...> A-alias points here)."
  value       = module.compute.alb_dns_name
}

output "ecr_repository_url" {
  value = module.compute.ecr_repository_url
}

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
  description = "Values the scripts consume (Fargate run-task needs subnets + SG)."
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
    subnets         = join(",", module.network.public_subnet_ids)
    security_group  = module.network.task_security_group_id
  }
}
