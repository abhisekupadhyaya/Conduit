output "db_instance_id" {
  value = aws_db_instance.this.identifier
}

output "db_address" {
  value = aws_db_instance.this.address
}

output "db_port" {
  value = aws_db_instance.this.port
}

# CONDUIT_DATABASE_URL form (matches backend/.env.example: asyncpg driver).
# TLS is enforced by the application (sslmode=require + RDS CA bundle, per
# infrastructure.md §SSL); kept out of the URL so the driver/connect-args
# own it rather than the DSN string.
output "database_url" {
  description = "postgresql+asyncpg connection URL for CONDUIT_DATABASE_URL."
  value       = "postgresql+asyncpg://${var.db_username}:${random_password.db.result}@${aws_db_instance.this.address}:${aws_db_instance.this.port}/${var.db_name}"
  sensitive   = true
}
