# -----------------------------------------------------------------------------
# Conduit — dev environment (the only environment; AD9 parameterised)
#
# Remote state in the bootstrap-created S3 bucket; every operation runs as the
# bootstrap-created ConduitTerraformOperator role (assume_role). Composes the
# modules into the full backend deployment.
# -----------------------------------------------------------------------------

terraform {
  required_version = ">= 1.5"

  required_providers {
    aws    = { source = "hashicorp/aws", version = "~> 5.0" }
    random = { source = "hashicorp/random", version = "~> 3.0" }
  }

  backend "s3" {
    bucket         = "conduit-terraform-state"
    key            = "conduit/dev/terraform.tfstate"
    region         = "us-east-1"
    dynamodb_table = "conduit-terraform-lock"
    encrypt        = true
    kms_key_id     = "alias/conduit-terraform-state"
  }
}

provider "aws" {
  region = var.aws_region

  assume_role {
    role_arn = var.terraform_role_arn
  }

  default_tags {
    tags = {
      Project     = "conduit"
      Environment = var.env
      ManagedBy   = "terraform"
    }
  }
}

locals {
  name_prefix = "conduit-${var.env}"
  api_fqdn    = "${var.api_subdomain}.${var.domain_name}"
}

module "network" {
  source      = "../../modules/network"
  name_prefix = local.name_prefix
  vpc_cidr    = var.vpc_cidr
}

module "data" {
  source                = "../../modules/data"
  name_prefix           = local.name_prefix
  private_subnet_ids    = module.network.private_subnet_ids
  rds_security_group_id = module.network.rds_security_group_id
  backup_retention_days = var.db_backup_retention_days
  deletion_protection   = var.db_deletion_protection
}

module "secrets" {
  source       = "../../modules/secrets"
  env          = var.env
  database_url = module.data.database_url
}

module "dns" {
  source        = "../../modules/dns"
  domain_name   = var.domain_name
  api_subdomain = var.api_subdomain
}

module "compute" {
  source                   = "../../modules/compute"
  name_prefix              = local.name_prefix
  env                      = var.env
  vpc_id                   = module.network.vpc_id
  public_subnet_ids        = module.network.public_subnet_ids
  alb_security_group_id    = module.network.alb_security_group_id
  task_security_group_id   = module.network.task_security_group_id
  certificate_arn          = module.dns.certificate_arn
  zone_id                  = module.dns.zone_id
  api_fqdn                 = module.dns.api_fqdn
  permissions_boundary_arn = var.permissions_boundary_arn
  frontend_origin          = var.frontend_origin
  secret_parameter_arns    = module.secrets.parameter_arns
  secret_names             = module.secrets.names
  image_tag                = var.image_tag
}

module "observability" {
  source         = "../../modules/observability"
  name_prefix    = local.name_prefix
  ops_email      = var.ops_email
  cluster_name   = module.compute.cluster_name
  service_name   = module.compute.service_name
  db_instance_id = module.data.db_instance_id
  log_group      = module.compute.log_group
}
