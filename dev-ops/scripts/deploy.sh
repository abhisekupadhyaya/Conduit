#!/usr/bin/env bash
#
# Build the backend image, push it to ECR, and roll the ECS service.
#
#   dev-ops/scripts/deploy.sh [env] [tag]
#
# First run also bumps the service desired count 0 -> 1 (the image-bootstrap
# decision: the service is created at 0 because ECR is empty on first apply).
#
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "${SCRIPT_DIR}/lib.sh"

ENV="${1:-dev}"
TAG="${2:-latest}"
conduit::need aws; conduit::need docker; conduit::need jq

CTX="$(conduit::context "${ENV}")"   # reads S3 state with caller creds
conduit::assume_operator              # ECR/ECS perms live on the operator role
REGION="$(jq -r .region <<<"${CTX}")"
CLUSTER="$(jq -r .cluster <<<"${CTX}")"
SERVICE="$(jq -r .service <<<"${CTX}")"
ECR="$(jq -r .ecr_repo <<<"${CTX}")"
REGISTRY="${ECR%%/*}"
BACKEND_DIR="$(conduit::repo_root)/backend"

echo "==> Logging in to ECR (${REGISTRY})"
aws ecr get-login-password --region "${REGION}" \
  | docker login --username AWS --password-stdin "${REGISTRY}"

echo "==> Building ${ECR}:${TAG} (linux/arm64 — t4g/Graviton)"
docker build --platform linux/arm64 \
  -t "${ECR}:${TAG}" -f "${BACKEND_DIR}/Dockerfile" "${BACKEND_DIR}"

echo "==> Pushing"
docker push "${ECR}:${TAG}"

echo "==> Ensuring service is up and rolling a new deployment"
aws ecs update-service --region "${REGION}" \
  --cluster "${CLUSTER}" --service "${SERVICE}" \
  --desired-count 1 --force-new-deployment >/dev/null

echo "==> Waiting for the service to stabilize"
aws ecs wait services-stable --region "${REGION}" \
  --cluster "${CLUSTER}" --services "${SERVICE}"

echo "Deployed ${ECR}:${TAG}."
