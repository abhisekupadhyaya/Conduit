# -----------------------------------------------------------------------------
# Conduit — Compute (AD1 ECS-on-EC2, AD2 Caddy on host, AD4 engine in-process)
#
# A single t4g.small (Graviton/ARM64) EC2 instance registered to an ECS
# cluster. The instance also runs Caddy, which terminates TLS (Let's Encrypt,
# auto-renew) and reverse-proxies api.<domain> -> the task on a static host
# port over loopback. No load balancer; the Elastic IP is the stable address.
#
# Three task definitions share one image: the API (engine runs in-process),
# a one-off Alembic migration task, and a one-off supervisor-seed task.
# -----------------------------------------------------------------------------

data "aws_region" "current" {}

# ECS-optimized Amazon Linux 2023 for ARM64 (t4g = Graviton).
data "aws_ssm_parameter" "ecs_ami" {
  name = "/aws/service/ecs/optimized-ami/amazon-linux-2023/arm64/recommended/image_id"
}

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

# --- IAM: ECS execution role (pull image, write logs, read SSM secrets) ----

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

# --- IAM: ECS task role (application runtime) ------------------------------

resource "aws_iam_role" "ecs_task" {
  name                 = "${var.name_prefix}-ecs-task"
  assume_role_policy   = data.aws_iam_policy_document.ecs_assume.json
  permissions_boundary = var.permissions_boundary_arn
}

# Object storage (S3) is a deliberate v1 deferral — backend behaviour is
# stubbed and no code path exercises CONDUIT_S3_*. When storage lands, attach
# a scoped s3 policy to this role + provision the bucket (additive change).

# --- IAM: EC2 container instance role --------------------------------------

data "aws_iam_policy_document" "ec2_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "ec2_instance" {
  name                 = "${var.name_prefix}-ec2-instance"
  assume_role_policy   = data.aws_iam_policy_document.ec2_assume.json
  permissions_boundary = var.permissions_boundary_arn
}

resource "aws_iam_role_policy_attachment" "ec2_ecs" {
  role       = aws_iam_role.ec2_instance.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonEC2ContainerServiceforEC2Role"
}

resource "aws_iam_instance_profile" "ec2_instance" {
  name = "${var.name_prefix}-ec2-instance"
  role = aws_iam_role.ec2_instance.name
}

# --- EC2 container instance + Caddy ---------------------------------------

locals {
  user_data = base64encode(templatefile("${path.module}/user-data.sh.tftpl", {
    cluster_name = aws_ecs_cluster.this.name
    api_fqdn     = var.api_fqdn
    acme_email   = var.acme_email
    host_port    = var.host_port
  }))
}

resource "aws_instance" "container" {
  ami                    = data.aws_ssm_parameter.ecs_ami.value
  instance_type          = var.instance_type
  subnet_id              = var.public_subnet_id
  vpc_security_group_ids = [var.ec2_security_group_id]
  iam_instance_profile   = aws_iam_instance_profile.ec2_instance.name
  user_data_base64       = local.user_data

  root_block_device {
    volume_size = 30
    volume_type = "gp3"
    encrypted   = true
  }

  tags = { Name = "${var.name_prefix}-container" }
}

resource "aws_eip_association" "container" {
  instance_id   = aws_instance.container.id
  allocation_id = var.eip_allocation_id
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

  # SSM-injected secrets, common to all task defs that talk to the DB.
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
}

resource "aws_ecs_task_definition" "api" {
  family                   = "${var.name_prefix}-api"
  requires_compatibilities = ["EC2"]
  network_mode             = "bridge"
  cpu                      = var.task_cpu
  memory                   = var.task_memory
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([{
    name             = "api"
    image            = "${aws_ecr_repository.backend.repository_url}:${var.image_tag}"
    essential        = true
    environment      = local.base_env
    secrets          = local.api_secrets
    portMappings     = [{ containerPort = var.host_port, hostPort = var.host_port, protocol = "tcp" }]
    logConfiguration = local.log_config
  }])
}

# One-off: alembic upgrade head (run via scripts/migrate.sh).
resource "aws_ecs_task_definition" "migrate" {
  family                   = "${var.name_prefix}-migrate"
  requires_compatibilities = ["EC2"]
  network_mode             = "bridge"
  cpu                      = var.task_cpu
  memory                   = var.task_memory
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

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

# One-off: bootstrap supervisor seed (run via scripts/seed.sh).
resource "aws_ecs_task_definition" "seed" {
  family                   = "${var.name_prefix}-seed"
  requires_compatibilities = ["EC2"]
  network_mode             = "bridge"
  cpu                      = var.task_cpu
  memory                   = var.task_memory
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

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
# Starts at desired_count = 0: first apply has no image in ECR yet. After
# scripts/deploy.sh pushes an image it bumps the count to 1 (the "image
# bootstrap" decision). Terraform ignores desired_count thereafter so the
# script owns it.

resource "aws_ecs_service" "api" {
  name            = "${var.name_prefix}-api"
  cluster         = aws_ecs_cluster.this.id
  task_definition = aws_ecs_task_definition.api.arn
  desired_count   = var.desired_count
  launch_type     = "EC2"

  deployment_minimum_healthy_percent = 0
  deployment_maximum_percent         = 100

  lifecycle {
    ignore_changes = [desired_count]
  }

  depends_on = [aws_instance.container]
}
