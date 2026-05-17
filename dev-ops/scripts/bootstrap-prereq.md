# Bootstrap prerequisite — the one manual IAM grant

Attach this policy to the IAM user that will run `terraform -chdir=dev-ops/terraform/bootstrap apply`.
It is the **only** permission a human is granted directly. Everything after
bootstrap runs as the `ConduitTerraformOperator` role (least privilege, capped
by `ConduitPermissionsBoundary`).

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "BootstrapStateBackend",
      "Effect": "Allow",
      "Action": ["s3:*", "dynamodb:*", "kms:*"],
      "Resource": "*",
      "Condition": { "StringEquals": { "aws:RequestedRegion": "us-east-1" } }
    },
    {
      "Sid": "BootstrapIAM",
      "Effect": "Allow",
      "Action": [
        "iam:CreateRole", "iam:DeleteRole", "iam:GetRole", "iam:TagRole",
        "iam:PutRolePolicy", "iam:GetRolePolicy", "iam:DeleteRolePolicy",
        "iam:CreatePolicy", "iam:DeletePolicy", "iam:GetPolicy",
        "iam:GetPolicyVersion", "iam:ListPolicyVersions",
        "iam:PutRolePermissionsBoundary", "iam:UpdateAssumeRolePolicy"
      ],
      "Resource": [
        "arn:aws:iam::*:role/ConduitTerraformOperator",
        "arn:aws:iam::*:policy/ConduitPermissionsBoundary"
      ]
    },
    {
      "Sid": "AssumeOperatorRole",
      "Effect": "Allow",
      "Action": "sts:AssumeRole",
      "Resource": "arn:aws:iam::*:role/ConduitTerraformOperator"
    },
    {
      "Sid": "WhoAmI",
      "Effect": "Allow",
      "Action": "sts:GetCallerIdentity",
      "Resource": "*"
    }
  ]
}
```

Adjust the region in `BootstrapStateBackend` if you change `aws_region`.
