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
        "iam:CreateRole", "iam:DeleteRole", "iam:GetRole",
        "iam:TagRole", "iam:UntagRole", "iam:ListRoleTags",
        "iam:PutRolePolicy", "iam:GetRolePolicy", "iam:DeleteRolePolicy",
        "iam:ListRolePolicies", "iam:ListAttachedRolePolicies",
        "iam:AttachRolePolicy", "iam:DetachRolePolicy",
        "iam:ListInstanceProfilesForRole",
        "iam:CreatePolicy", "iam:DeletePolicy", "iam:GetPolicy",
        "iam:GetPolicyVersion", "iam:ListPolicyVersions",
        "iam:CreatePolicyVersion", "iam:DeletePolicyVersion",
        "iam:ListEntitiesForPolicy",
        "iam:TagPolicy", "iam:UntagPolicy", "iam:ListPolicyTags",
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

> **Note.** The IAM action list is exactly what the Terraform AWS provider
> calls across the role/policy lifecycle (it reads inline + attached policies
> and instance profiles after every create/refresh). Bootstrap is a one-time
> privileged step; if scoping this policy precisely is not worth it for your
> account, running bootstrap once as an existing **admin/`IAMFullAccess`**
> identity is a legitimate alternative — the security model lives in the
> `ConduitTerraformOperator` role + `ConduitPermissionsBoundary` it creates,
> **not** in starving the one-time bootstrap principal.
