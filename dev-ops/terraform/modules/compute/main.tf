# -----------------------------------------------------------------------------
# Conduit — Compute (ECS Fargate + ALB + ACM)
#
# Pivoted from ECS-on-EC2 + Caddy: no EC2 host, no user-data, no Let's Encrypt.
# An ALB terminates TLS with the AWS-managed ACM cert and forwards to Fargate
# tasks (awsvpc, ARM64 to match the pushed image). One image, three task
# defs: API (engine in-process, AD4), one-off migrate, one-off seed.
# -----------------------------------------------------------------------------

data "aws_region" "current" {}

resource "aws_ecs_cluster" "this" {
  name = "${var.name_prefix}-cluster"
}

# --- ECR -------------------------------------------------------------------

resource "aws_ecr_repository" "backend" {
  name                 = "${var.name_prefix}-backend"
  image_tag_mutability = "MUTABLE"
  image_scanning_configuration {
    scan_on_push = true
  }
}

resource "aws_ecr_lifecycle_policy" "backend" {
  repository = aws_ecr_repository.backend.name
  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Keep last 10 images"
      selection    = { tagStatus = "any", countType = "imageCountMoreThan", countNumber = 10 }
      action       = { type = "expire" }
    }]
  })
}

# --- Logs ------------------------------------------------------------------

resource "aws_cloudwatch_log_group" "backend" {
  name              = "/conduit/${var.env}/backend"
  retention_in_days = 7
}

# --- IAM -------------------------------------------------------------------

data "aws_iam_policy_document" "ecs_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "ecs_execution" {
  name                 = "${var.name_prefix}-ecs-execution"
  assume_role_policy   = data.aws_iam_policy_document.ecs_assume.json
  permissions_boundary = var.permissions_boundary_arn
}

resource "aws_iam_role_policy_attachment" "ecs_execution_managed" {
  role       = aws_iam_role.ecs_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_iam_role_policy" "ecs_execution_ssm" {
  name = "read-ssm-secrets"
  role = aws_iam_role.ecs_execution.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "ReadSecureParams"
        Effect   = "Allow"
        Action   = ["ssm:GetParameters"]
        Resource = var.secret_parameter_arns
      },
      {
        Sid      = "DecryptSecureParams"
        Effect   = "Allow"
        Action   = ["kms:Decrypt"]
        Resource = "*"
        Condition = {
          StringEquals = { "kms:ViaService" = "ssm.${data.aws_region.current.name}.amazonaws.com" }
        }
      }
    ]
  })
}

resource "aws_iam_role" "ecs_task" {
  name                 = "${var.name_prefix}-ecs-task"
  assume_role_policy   = data.aws_iam_policy_document.ecs_assume.json
  permissions_boundary = var.permissions_boundary_arn
}

# Object storage (S3) is a deliberate v1 deferral — backend behaviour is
# stubbed and no code path exercises CONDUIT_S3_*. When storage lands, attach
# a scoped s3 policy to this role + provision the bucket (additive change).

# --- ALB -------------------------------------------------------------------

resource "aws_lb" "this" {
  name               = "${var.name_prefix}-alb"
  load_balancer_type = "application"
  internal           = false
  subnets            = var.public_subnet_ids
  security_groups    = [var.alb_security_group_id]
}

resource "aws_lb_target_group" "api" {
  name        = "${var.name_prefix}-api"
  port        = var.container_port
  protocol    = "HTTP"
  vpc_id      = var.vpc_id
  target_type = "ip" # required for awsvpc/Fargate

  health_check {
    path     = "/"
    protocol = "HTTP"
    # Endpoints are stubs in v1; any HTTP response means the app is up.
    matcher  = "200-499"
    interval = 30
    timeout  = 5
  }
}

resource "aws_lb_listener" "https" {
  load_balancer_arn = aws_lb.this.arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn   = var.certificate_arn

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api.arn
  }
}

resource "aws_lb_listener" "http_redirect" {
  load_balancer_arn = aws_lb.this.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type = "redirect"
    redirect {
      port        = "443"
      protocol    = "HTTPS"
      status_code = "HTTP_301"
    }
  }
}

# A-alias: api.<sub>.<zone> -> ALB (zone is the existing one from the dns module)
resource "aws_route53_record" "api" {
  zone_id = var.zone_id
  name    = var.api_fqdn
  type    = "A"

  alias {
    name                   = aws_lb.this.dns_name
    zone_id                = aws_lb.this.zone_id
    evaluate_target_health = true
  }
}

# --- Task definitions ------------------------------------------------------

locals {
  log_config = {
    logDriver = "awslogs"
    options = {
      "awslogs-group"         = aws_cloudwatch_log_group.backend.name
      "awslogs-region"        = data.aws_region.current.name
      "awslogs-stream-prefix" = "conduit"
    }
  }

  db_secrets = [
    { name = "CONDUIT_DATABASE_URL", valueFrom = var.secret_names.database_url },
  ]

  api_secrets = concat(local.db_secrets, [
    { name = "CONDUIT_JWT_SECRET", valueFrom = var.secret_names.jwt_secret },
    { name = "CONDUIT_OPENAI_API_KEY", valueFrom = var.secret_names.openai_api_key },
  ])

  seed_secrets = concat(local.db_secrets, [
    { name = "CONDUIT_SEED_SUPERVISOR_USERNAME", valueFrom = var.secret_names.seed_supervisor_username },
    { name = "CONDUIT_SEED_SUPERVISOR_PASSWORD", valueFrom = var.secret_names.seed_supervisor_password },
  ])

  base_env = [
    { name = "CONDUIT_ENV", value = var.env },
    { name = "CONDUIT_API_PREFIX", value = "/api" },
    { name = "CONDUIT_CORS_ORIGINS", value = var.frontend_origin },
    { name = "CONDUIT_COOKIE_SECURE", value = "true" },
    { name = "CONDUIT_COOKIE_SAMESITE", value = "lax" },
    { name = "CONDUIT_OPENAI_MODEL", value = var.openai_model },
    { name = "CONDUIT_ENGINE_ENABLED", value = "true" },
    { name = "CONDUIT_ENGINE_POLL_SECONDS", value = "10" },
  ]

  runtime_platform = {
    operating_system_family = "LINUX"
    cpu_architecture        = "ARM64" # image was built --platform linux/arm64
  }
}

resource "aws_ecs_task_definition" "api" {
  family                   = "${var.name_prefix}-api"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.api_cpu
  memory                   = var.api_memory
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  runtime_platform {
    operating_system_family = local.runtime_platform.operating_system_family
    cpu_architecture        = local.runtime_platform.cpu_architecture
  }

  container_definitions = jsonencode([{
    name             = "api"
    image            = "${aws_ecr_repository.backend.repository_url}:${var.image_tag}"
    essential        = true
    environment      = local.base_env
    secrets          = local.api_secrets
    portMappings     = [{ containerPort = var.container_port, protocol = "tcp" }]
    logConfiguration = local.log_config
  }])
}

resource "aws_ecs_task_definition" "migrate" {
  family                   = "${var.name_prefix}-migrate"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.oneoff_cpu
  memory                   = var.oneoff_memory
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  runtime_platform {
    operating_system_family = local.runtime_platform.operating_system_family
    cpu_architecture        = local.runtime_platform.cpu_architecture
  }

  container_definitions = jsonencode([{
    name             = "migrate"
    image            = "${aws_ecr_repository.backend.repository_url}:${var.image_tag}"
    essential        = true
    command          = ["alembic", "upgrade", "head"]
    environment      = local.base_env
    secrets          = local.db_secrets
    logConfiguration = local.log_config
  }])
}

resource "aws_ecs_task_definition" "seed" {
  family                   = "${var.name_prefix}-seed"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.oneoff_cpu
  memory                   = var.oneoff_memory
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  runtime_platform {
    operating_system_family = local.runtime_platform.operating_system_family
    cpu_architecture        = local.runtime_platform.cpu_architecture
  }

  container_definitions = jsonencode([{
    name             = "seed"
    image            = "${aws_ecr_repository.backend.repository_url}:${var.image_tag}"
    essential        = true
    command          = ["python", "-m", "conduit.seed"]
    environment      = local.base_env
    secrets          = local.seed_secrets
    logConfiguration = local.log_config
  }])
}

# --- Service ---------------------------------------------------------------
# Starts at desired_count = 0 (no image on first apply); scripts/deploy.sh
# pushes the image and bumps to 1. Terraform ignores desired_count after.

resource "aws_ecs_service" "api" {
  name            = "${var.name_prefix}-api"
  cluster         = aws_ecs_cluster.this.id
  task_definition = aws_ecs_task_definition.api.arn
  desired_count   = var.desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = var.public_subnet_ids
    security_groups  = [var.task_security_group_id]
    assign_public_ip = true # public subnet + IGW egress (no NAT)
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.api.arn
    container_name   = "api"
    container_port   = var.container_port
  }

  health_check_grace_period_seconds = 60

  lifecycle {
    ignore_changes = [desired_count]
  }

  depends_on = [aws_lb_listener.https]
}
