#!/usr/bin/env bash
# Promote the images scripts/publish.sh pushed for $IMAGE_TAG to the two Azure Container
# Apps, by digest, then verify. Runs inside the shared FO-AI reusable-azure-cd wrapper,
# which has already checked out the commit, rejected a stale main, and signed in to Azure.
# Never builds.
#
# App settings and secrets are managed on the Container Apps themselves, not by this script.
#
# Part of the FO-AI repository script contract (scripts/ci.sh, scripts/publish.sh,
# scripts/cd.sh); see the FO-AI/automation README and docs/CI-CD.md.
#
# From the wrapper: DEPLOY_SHA, IMAGE_TAG, GH_TOKEN, DEPLOYMENT_VARS_JSON,
#                   API_ENV_FILE, WEB_ENV_FILE.
#
# STATUS: implemented. Replaces the deploy half of scripts/docker-build-and-push.sh.
# Reference implementation: FO-AI/nimbus scripts/cd.sh.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

: "${RUNNER_TEMP:?RUNNER_TEMP is required}"
: "${GITHUB_STEP_SUMMARY:?GITHUB_STEP_SUMMARY is required}"
: "${IMAGE_TAG:?IMAGE_TAG must be the source commit selected by the shared workflow}"
: "${DEPLOY_SHA:?DEPLOY_SHA is required}"
: "${GITHUB_REPOSITORY:?GITHUB_REPOSITORY is required}"
: "${GH_TOKEN:?GH_TOKEN is required for the final main-branch check}"
: "${DEPLOYMENT_VARS_JSON:?DEPLOYMENT_VARS_JSON is required}"
if [[ ! "$IMAGE_TAG" =~ ^[0-9a-f]{40}$ ]]; then
  echo '::error::IMAGE_TAG must be a full commit SHA; publish.sh tags images by it'
  exit 1
fi

unset API_ENV_FILE
unset WEB_ENV_FILE

eval "$(python3 - <<'PY'
import json
import os
import shlex
import sys

required = (
    "RESOURCE_GROUP",
    "ACR_NAME",
    "BACKEND_APP_NAME",
    "FRONTEND_APP_NAME",
    "BACKEND_URL",
    "FRONTEND_URL",
)

try:
    data = json.loads(os.environ["DEPLOYMENT_VARS_JSON"])
except json.JSONDecodeError:
    print("::error::DEPLOYMENT_VARS_JSON is not valid JSON", file=sys.stderr)
    sys.exit(1)

if not isinstance(data, dict):
    print("::error::DEPLOYMENT_VARS_JSON must be a JSON object", file=sys.stderr)
    sys.exit(1)

missing = [name for name in required if not str(data.get(name) or "").strip()]
if missing:
    print(
        "::error::Missing deployment setting(s): " + ", ".join(missing),
        file=sys.stderr,
    )
    sys.exit(1)

for name in required:
    value = data.get(name)
    if value is None or not str(value).strip():
        continue
    print(f"{name}={shlex.quote(str(value))}")
PY
)"

az config set \
  extension.use_dynamic_install=yes_without_prompt \
  extension.dynamic_install_allow_preview=true \
  --only-show-errors

az containerapp show --name "$BACKEND_APP_NAME" --resource-group "$RESOURCE_GROUP" --output none
az containerapp show --name "$FRONTEND_APP_NAME" --resource-group "$RESOURCE_GROUP" --output none

digest_for() {
  local service="$1"
  local digest
  digest="$(az acr repository show \
    --name "$ACR_NAME" \
    --image "charlotte-${service}:${IMAGE_TAG}" \
    --query digest -o tsv)"
  if [[ ! "$digest" =~ ^sha256:[0-9a-f]{64}$ ]]; then
    printf '::error::charlotte-%s:%s did not resolve to a sha256 digest (got %q)\n' \
      "$service" "$IMAGE_TAG" "$digest"
    exit 1
  fi
  printf '%s\n' "$digest"
}

BACKEND_DIGEST="$(digest_for backend)"
FRONTEND_DIGEST="$(digest_for frontend)"
BACKEND_IMAGE="$ACR_NAME.azurecr.io/charlotte-backend@$BACKEND_DIGEST"
FRONTEND_IMAGE="$ACR_NAME.azurecr.io/charlotte-frontend@$FRONTEND_DIGEST"

main_sha="$(gh api "repos/${GITHUB_REPOSITORY}/git/ref/heads/main" --jq '.object.sha')"
if [[ "$DEPLOY_SHA" != "$main_sha" ]]; then
  echo '::error::Refusing stale deployment'
  exit 1
fi

az containerapp update \
  --name "$BACKEND_APP_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --image "$BACKEND_IMAGE" \
  --output none

az containerapp update \
  --name "$FRONTEND_APP_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --image "$FRONTEND_IMAGE" \
  --output none

verify_health() {
  curl --fail --silent --show-error --retry 30 --retry-delay 10 --retry-all-errors \
    "$BACKEND_URL/api/health" > /dev/null
  curl --fail --silent --show-error --retry 30 --retry-delay 10 --retry-all-errors \
    "$FRONTEND_URL" > /dev/null
}

if ! verify_health; then
  echo '::error::Health check did not pass after deploying Container Apps'
  az containerapp revision list \
    --name "$BACKEND_APP_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --query "[].{revision:name,active:properties.active,health:properties.healthState,running:properties.runningState}" \
    -o table
  az containerapp revision list \
    --name "$FRONTEND_APP_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --query "[].{revision:name,active:properties.active,health:properties.healthState,running:properties.runningState}" \
    -o table
  exit 1
fi

BACKEND_REVISION="$(az containerapp show \
  --name "$BACKEND_APP_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --query properties.latestRevisionName -o tsv)"
FRONTEND_REVISION="$(az containerapp show \
  --name "$FRONTEND_APP_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --query properties.latestRevisionName -o tsv)"

{
  echo "### Deployed images"
  echo ""
  echo "- commit: \`$DEPLOY_SHA\`"
  echo "- tag: \`$IMAGE_TAG\`"
  echo "- \`$BACKEND_IMAGE\`"
  echo "- \`$FRONTEND_IMAGE\`"
  echo "- backend revision: \`$BACKEND_REVISION\`"
  echo "- frontend revision: \`$FRONTEND_REVISION\`"
  echo "- backend: $BACKEND_URL"
  echo "- frontend: $FRONTEND_URL"
} >> "$GITHUB_STEP_SUMMARY"
