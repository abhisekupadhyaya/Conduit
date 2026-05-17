# ARNs the ECS execution role is granted ssm:GetParameters on, and the names
# the task definition references for secret injection.

output "parameter_arns" {
  value = [
    aws_ssm_parameter.database_url.arn,
    aws_ssm_parameter.jwt_secret.arn,
    aws_ssm_parameter.openai_api_key.arn,
    aws_ssm_parameter.seed_supervisor_username.arn,
    aws_ssm_parameter.seed_supervisor_password.arn,
  ]
}

output "names" {
  description = "Map of logical name -> SSM parameter name for task-def secrets."
  value = {
    database_url             = aws_ssm_parameter.database_url.name
    jwt_secret               = aws_ssm_parameter.jwt_secret.name
    openai_api_key           = aws_ssm_parameter.openai_api_key.name
    seed_supervisor_username = aws_ssm_parameter.seed_supervisor_username.name
    seed_supervisor_password = aws_ssm_parameter.seed_supervisor_password.name
  }
}

output "path_prefix" {
  value = local.prefix
}
