#!/usr/bin/env bash
#
# Run database migrations as a one-off ECS task (alembic upgrade head).
#
#   dev-ops/scripts/migrate.sh [env]
#
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "${SCRIPT_DIR}/lib.sh"

conduit::run_oneoff "${1:-dev}" migrate_task
