output "vpc_id" {
  value = aws_vpc.this.id
}

output "public_subnet_id" {
  value = aws_subnet.public.id
}

output "private_subnet_ids" {
  value = aws_subnet.private[*].id
}

output "ec2_security_group_id" {
  value = aws_security_group.ec2.id
}

output "rds_security_group_id" {
  value = aws_security_group.rds.id
}

output "eip_allocation_id" {
  value = aws_eip.api.allocation_id
}

output "eip_public_ip" {
  description = "Stable public IP — the Route53 A record and ACME challenge target."
  value       = aws_eip.api.public_ip
}
