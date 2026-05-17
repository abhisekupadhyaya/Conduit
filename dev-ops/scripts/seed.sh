#!/usr/bin/env bash
#
# Seed the bootstrap supervisor as a one-off ECS task (python -m conduit.seed).
# Idempotent — re-running is safe (conduit.seed upserts the supervisor).
#
#   dev-ops/scripts/seed.sh [env]
#
# Requires the seed supervisor credentials to be set first:
#   dev-ops/scripts/set-secrets.sh <env>
#
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "${SCRIPT_DIR}/lib.sh"

conduit::run_oneoff "${1:-dev}" seed_task
