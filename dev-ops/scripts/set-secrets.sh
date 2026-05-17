#!/usr/bin/env bash
#
# Write the operator-supplied secret VALUES into SSM SecureString parameters.
# Terraform created these parameters with a "REPLACE_ME" placeholder and
# ignore_changes on value, so real secrets never enter Terraform state.
#
#   dev-ops/scripts/set-secrets.sh [env]
#
# Prompts (no echo) for: OpenAI API key, seed supervisor username + password.
# database_url and jwt_secret are Terraform-owned and already set.
#
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "${SCRIPT_DIR}/lib.sh"

ENV="${1:-dev}"
conduit::need aws; conduit::need jq

CTX="$(conduit::context "${ENV}")"   # reads S3 state with caller creds
conduit::assume_operator              # ssm:PutParameter lives on the operator role
REGION="$(jq -r .region <<<"${CTX}")"
PREFIX="$(jq -r .ssm_path_prefix <<<"${CTX}")"

put() {
  local name="$1" value="$2"
  aws ssm put-parameter --region "${REGION}" \
    --name "${PREFIX}/${name}" --type SecureString \
    --value "${value}" --overwrite >/dev/null
  echo "    set ${PREFIX}/${name}"
}

read -rs -p "OpenAI API key: " OPENAI; echo
read -r  -p "Seed supervisor username: " SUSER
read -rs -p "Seed supervisor password: " SPASS; echo

echo "==> Writing SSM SecureString values"
put CONDUIT_OPENAI_API_KEY "${OPENAI}"
put CONDUIT_SEED_SUPERVISOR_USERNAME "${SUSER}"
put CONDUIT_SEED_SUPERVISOR_PASSWORD "${SPASS}"

echo "Done. Now: deploy.sh -> migrate.sh -> seed.sh"
