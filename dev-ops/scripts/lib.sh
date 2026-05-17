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

# conduit::run_oneoff <env> <task_family_key>
# Runs a one-off ECS task (EC2 launch type) to completion, tails its logs,
# and exits non-zero if the container exited non-zero.
conduit::run_oneoff() {
  local env="$1" task_key="$2"
  conduit::need aws; conduit::need jq

  local ctx region cluster family log_group
  ctx="$(conduit::context "${env}")"
  region="$(jq -r .region <<<"${ctx}")"
  cluster="$(jq -r .cluster <<<"${ctx}")"
  family="$(jq -r ".${task_key}" <<<"${ctx}")"
  log_group="$(jq -r .log_group <<<"${ctx}")"

  echo "==> Running one-off task: ${family}"
  local arn
  arn="$(aws ecs run-task --region "${region}" --cluster "${cluster}" \
    --task-definition "${family}" --launch-type EC2 --count 1 \
    --query 'tasks[0].taskArn' --output text)"
  [ -n "${arn}" ] && [ "${arn}" != "None" ] || { echo "run-task failed (no capacity?)" >&2; return 1; }

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
