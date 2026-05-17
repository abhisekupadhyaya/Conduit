output "cluster_name" {
  value = aws_ecs_cluster.this.name
}

output "service_name" {
  value = aws_ecs_service.api.name
}

output "ecr_repository_url" {
  value = aws_ecr_repository.backend.repository_url
}

output "api_task_family" {
  value = aws_ecs_task_definition.api.family
}

output "migrate_task_family" {
  value = aws_ecs_task_definition.migrate.family
}

output "seed_task_family" {
  value = aws_ecs_task_definition.seed.family
}

output "log_group" {
  value = aws_cloudwatch_log_group.backend.name
}

output "alb_dns_name" {
  value = aws_lb.this.dns_name
}
