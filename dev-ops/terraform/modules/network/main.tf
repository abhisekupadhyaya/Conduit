# -----------------------------------------------------------------------------
# Conduit — Network (Fargate + ALB; no NAT, egress via IGW)
#
# Two public subnets host the ALB and the Fargate tasks (tasks get a public IP
# so they reach ECR/SSM/OpenAI over the Internet Gateway — preserves the
# deliberate no-NAT cost decision). Two private subnets host RDS.
#
#   internet → alb_sg(80,443) → ALB → task_sg(8000) → Fargate → rds_sg(5432) → RDS
# -----------------------------------------------------------------------------

data "aws_availability_zones" "available" {
  state = "available"
}

locals {
  azs = slice(data.aws_availability_zones.available.names, 0, 2)
}

resource "aws_vpc" "this" {
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true
  tags                 = { Name = "${var.name_prefix}-vpc" }
}

resource "aws_internet_gateway" "this" {
  vpc_id = aws_vpc.this.id
  tags   = { Name = "${var.name_prefix}-igw" }
}

# --- Public subnets: ALB + Fargate tasks (2 AZs, ALB requires >=2) ---------

resource "aws_subnet" "public" {
  count                   = 2
  vpc_id                  = aws_vpc.this.id
  cidr_block              = cidrsubnet(var.vpc_cidr, 8, count.index)
  availability_zone       = local.azs[count.index]
  map_public_ip_on_launch = true
  tags                    = { Name = "${var.name_prefix}-public-${count.index}" }
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.this.id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.this.id
  }
  tags = { Name = "${var.name_prefix}-public-rt" }
}

resource "aws_route_table_association" "public" {
  count          = 2
  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

# --- Private subnets: RDS (no internet route) ------------------------------

resource "aws_subnet" "private" {
  count             = 2
  vpc_id            = aws_vpc.this.id
  cidr_block        = cidrsubnet(var.vpc_cidr, 8, count.index + 10)
  availability_zone = local.azs[count.index]
  tags              = { Name = "${var.name_prefix}-private-${count.index}" }
}

resource "aws_route_table" "private" {
  vpc_id = aws_vpc.this.id
  tags   = { Name = "${var.name_prefix}-private-rt" }
}

resource "aws_route_table_association" "private" {
  count          = 2
  subnet_id      = aws_subnet.private[count.index].id
  route_table_id = aws_route_table.private.id
}

# --- Security groups -------------------------------------------------------

resource "aws_security_group" "alb" {
  name        = "${var.name_prefix}-alb"
  description = "Conduit ALB: 80/443 from the internet."
  vpc_id      = aws_vpc.this.id

  ingress {
    description = "HTTPS"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  ingress {
    description = "HTTP (redirect to HTTPS)"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  egress {
    description = "To Fargate tasks"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
  tags = { Name = "${var.name_prefix}-alb" }
}

resource "aws_security_group" "task" {
  name        = "${var.name_prefix}-task"
  description = "Conduit Fargate tasks: app port from ALB only; all egress (ECR/SSM/OpenAI/RDS via IGW)."
  vpc_id      = aws_vpc.this.id

  ingress {
    description     = "App port from ALB"
    from_port       = var.container_port
    to_port         = var.container_port
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }
  egress {
    description = "All egress"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
  tags = { Name = "${var.name_prefix}-task" }
}

resource "aws_security_group" "rds" {
  name = "${var.name_prefix}-rds"
  # SG description is immutable in AWS; changing it forces a replace, and an
  # SG attached to RDS cannot be replaced cleanly (RDS-owned ENIs are not
  # user-detachable). This string is intentionally pinned to the originally
  # deployed value so the EC2->Fargate pivot is an in-place ingress update,
  # not a destroy/recreate. (Functionally it is now "from Fargate tasks".)
  description = "Conduit RDS: 5432 only from the EC2 container instance."
  vpc_id      = aws_vpc.this.id

  ingress {
    description     = "PostgreSQL from tasks"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.task.id]
  }
  tags = { Name = "${var.name_prefix}-rds" }
}
