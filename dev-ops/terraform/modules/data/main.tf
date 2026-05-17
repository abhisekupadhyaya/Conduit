# -----------------------------------------------------------------------------
# Conduit — Data (AD3: managed RDS Postgres, single-AZ t4g.micro, PITR)
#
# The product invariant is "nothing is silently lost"; that durability lives
# here, so the database is the one component deliberately NOT cost-optimised:
# managed, encrypted, automated backups + point-in-time recovery. Single-AZ is
# the accepted availability trade (never a data trade).
# -----------------------------------------------------------------------------

resource "random_password" "db" {
  length  = 32
  special = false # keep the URL form simple; 32 alnum chars is ample entropy
}

resource "aws_db_subnet_group" "this" {
  name       = "${var.name_prefix}-db"
  subnet_ids = var.private_subnet_ids
  tags       = { Name = "${var.name_prefix}-db" }
}

resource "aws_db_instance" "this" {
  identifier     = "${var.name_prefix}-pg"
  engine         = "postgres"
  engine_version = var.engine_version
  instance_class = "db.t4g.micro"

  allocated_storage     = 20
  max_allocated_storage = 100
  storage_type          = "gp3"
  storage_encrypted     = true

  db_name  = var.db_name
  username = var.db_username
  password = random_password.db.result
  port     = 5432

  db_subnet_group_name   = aws_db_subnet_group.this.name
  vpc_security_group_ids = [var.rds_security_group_id]
  multi_az               = false
  publicly_accessible    = false

  # PITR: automated backups retained; the durability promise.
  backup_retention_period   = var.backup_retention_days
  copy_tags_to_snapshot     = true
  deletion_protection       = var.deletion_protection
  skip_final_snapshot       = false
  final_snapshot_identifier = "${var.name_prefix}-pg-final"

  auto_minor_version_upgrade = true
  apply_immediately          = false

  tags = { Name = "${var.name_prefix}-pg" }
}
