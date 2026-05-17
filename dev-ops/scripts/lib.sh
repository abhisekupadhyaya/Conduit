#!/usr/bin/env bash
# Shared helpers for the Conduit deploy scripts. Sourced, not executed.
set -euo pipefail

conduit::repo_root() {
  git -C "$(dirname "${BASH_SOURCE[0]}")" rev-parse --show-toplevel
}

# Echo the environments/<env> deploy_context as compact JSON.
conduit::context() {
  local env="$1" tf_dir
  tf_dir="$(conduit::repo_root)/dev-ops/terraform/environments/${env}"
  terraform -chdir="${tf_dir}" output -json deploy_context
}

conduit::need() {
  command -v "$1" >/dev/null 2>&1 || { echo "error: '$1' not found in PATH" >&2; exit 1; }
}

# Assume ConduitTerraformOperator and export temp creds for the rest of the
# script. The human/bootstrap principal only has S3/DynamoDB/KMS + AssumeRole;
# all runtime perms (ssm, ecs, ecr, logs) live on the operator role — the same
# role the Terraform provider assumes. Idempotent; skip with
# CONDUIT_SKIP_ASSUME=1 if your shell already holds operator/admin creds.
conduit::assume_operator() {
  [ "${CONDUIT_SKIP_ASSUME:-0}" = "1" ] && return 0
  conduit::need aws; conduit::need jq
  local acct role creds
  acct="$(aws sts get-caller-identity --query Account --output text)"
  role="arn:aws:iam::${acct}:role/ConduitTerraformOperator"
  creds="$(aws sts assume-role --role-arn "${role}" \
    --role-session-name conduit-ops --query Credentials --output json)"
  AWS_ACCESS_KEY_ID="$(jq -r .AccessKeyId <<<"${creds}")"
  AWS_SECRET_ACCESS_KEY="$(jq -r .SecretAccessKey <<<"${creds}")"
  AWS_SESSION_TOKEN="$(jq -r .SessionToken <<<"${creds}")"
  export AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN
}

# conduit::run_oneoff <env> <task_family_key>
# Runs a one-off ECS Fargate task to completion, tails its logs, and exits
# non-zero if the container exited non-zero.
conduit::run_oneoff() {
  local env="$1" task_key="$2"
  conduit::need aws; conduit::need jq

  local ctx region cluster family log_group subnets sg
  ctx="$(conduit::context "${env}")"   # reads S3 state with caller creds
  conduit::assume_operator              # switch to runtime perms after
  region="$(jq -r .region <<<"${ctx}")"
  cluster="$(jq -r .cluster <<<"${ctx}")"
  family="$(jq -r ".${task_key}" <<<"${ctx}")"
  log_group="$(jq -r .log_group <<<"${ctx}")"
  subnets="$(jq -r .subnets <<<"${ctx}")"
  sg="$(jq -r .security_group <<<"${ctx}")"

  echo "==> Running one-off task: ${family}"
  local arn
  arn="$(aws ecs run-task --region "${region}" --cluster "${cluster}" \
    --task-definition "${family}" --launch-type FARGATE --count 1 \
    --network-configuration "awsvpcConfiguration={subnets=[${subnets}],securityGroups=[${sg}],assignPublicIp=ENABLED}" \
    --query 'tasks[0].taskArn' --output text)"
  [ -n "${arn}" ] && [ "${arn}" != "None" ] || { echo "run-task failed" >&2; return 1; }

  echo "    task ${arn##*/} — waiting for it to stop"
  aws ecs wait tasks-stopped --region "${region}" --cluster "${cluster}" --tasks "${arn}"

  echo "==> Logs:"
  aws logs tail "${log_group}" --region "${region}" --since 15m || true

  local code
  code="$(aws ecs describe-tasks --region "${region}" --cluster "${cluster}" \
    --tasks "${arn}" --query 'tasks[0].containers[0].exitCode' --output text)"
  echo "==> Exit code: ${code}"
  [ "${code}" = "0" ]
}
