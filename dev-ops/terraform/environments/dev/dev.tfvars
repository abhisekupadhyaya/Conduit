# From bootstrap outputs:
terraform_role_arn       = "arn:aws:iam::455349221632:role/ConduitTerraformOperator"
permissions_boundary_arn = "arn:aws:iam::455349221632:policy/ConduitPermissionsBoundary"

aws_region = "us-east-1"

# Existing Route 53 zone (looked up, not created). API host = api.conduit.narv.ai
domain_name   = "narv.ai"
api_subdomain = "api.conduit"

# Frontend is hosted at conduit.narv.ai (confirmed). Exact single origin —
# scheme+host, no trailing slash, no wildcard — written to CONDUIT_CORS_ORIGINS
# on the API task (backend owns CORS, AD6 divergence).
frontend_origin = "https://conduit.narv.ai"

ops_email = "abhisek.upadhyaya11@gmail.com"
