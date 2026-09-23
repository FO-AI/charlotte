#!/usr/bin/env bash
# Promote the images scripts/publish.sh pushed for $IMAGE_TAG to the two App Service web
# apps, by digest, then verify. Runs inside the shared FO-AI reusable-azure-cd wrapper,
# which has already checked out the commit, rejected a stale main, and signed in to Azure.
# Never builds.
#
# Part of the FO-AI repository script contract (scripts/ci.sh, scripts/publish.sh,
# scripts/cd.sh); see the FO-AI/automation README and docs/CI-CD.md.
#
# From the wrapper: DEPLOY_SHA, IMAGE_TAG, GH_TOKEN, DEPLOYMENT_VARS_JSON,
#                   API_ENV_FILE, WEB_ENV_FILE.
#
# STATUS: implemented. Replaces the deploy half of scripts/docker-build-and-push.sh.
# Reference implementation: FO-AI/nimbus scripts/cd.sh. Nimbus deploys to Container Apps;
# Charlotte runs on App Service, so the `az` commands differ but the order is the same.
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

BACKEND_ENV_FILE="$RUNNER_TEMP/charlotte-backend.env"
BACKEND_SETTINGS_JSON="$RUNNER_TEMP/charlotte-backend.settings.json"
FRONTEND_SETTINGS_JSON="$RUNNER_TEMP/charlotte-frontend.settings.json"

cleanup() {
  rm -f "$BACKEND_ENV_FILE" "$BACKEND_SETTINGS_JSON" "$FRONTEND_SETTINGS_JSON"
}
trap cleanup EXIT

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
optional = (
    "NEXT_PUBLIC_API_BASE_URL",
    "NEXT_PUBLIC_AZURE_AD_CLIENT_ID",
    "NEXT_PUBLIC_AZURE_AD_TENANT_ID",
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

for name in (*required, *optional):
    value = data.get(name)
    if value is None or not str(value).strip():
        continue
    print(f"{name}={shlex.quote(str(value))}")
PY
)"

if [[ -z "${API_ENV_FILE:-}" ]]; then
  echo '::error::API_ENV_FILE is required (set it as a secret on the dev environment)'
  exit 1
fi

umask 077
printf '%s' "$API_ENV_FILE" > "$BACKEND_ENV_FILE"
unset API_ENV_FILE
unset WEB_ENV_FILE

az webapp show --name "$BACKEND_APP_NAME" --resource-group "$RESOURCE_GROUP" --output none
az webapp show --name "$FRONTEND_APP_NAME" --resource-group "$RESOURCE_GROUP" --output none

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

python3 - "$BACKEND_ENV_FILE" "$BACKEND_SETTINGS_JSON" <<'PY'
import json
import sys

src, dest = sys.argv[1], sys.argv[2]
settings = []
with open(src, encoding="utf-8") as handle:
    for raw in handle:
        line = raw.strip().lstrip("\ufeff")
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            print("::error::API_ENV_FILE has a line without '='", file=sys.stderr)
            sys.exit(1)
        name, value = line.split("=", 1)
        name = name.strip()
        if not name.isidentifier():
            print("::error::API_ENV_FILE has an invalid setting name", file=sys.stderr)
            sys.exit(1)
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        settings.append({"name": name, "value": value, "slotSetting": False})

if not settings:
    print("::error::API_ENV_FILE contained no settings", file=sys.stderr)
    sys.exit(1)

with open(dest, "w", encoding="utf-8") as handle:
    json.dump(settings, handle)
PY

az webapp config appsettings set \
  --name "$BACKEND_APP_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --settings @"$BACKEND_SETTINGS_JSON" \
  --output none

python3 - "$FRONTEND_SETTINGS_JSON" <<'PY'
import json
import os
import sys

settings = [{"name": "NODE_ENV", "value": "production", "slotSetting": False}]
for name in (
    "NEXT_PUBLIC_API_BASE_URL",
    "NEXT_PUBLIC_AZURE_AD_CLIENT_ID",
    "NEXT_PUBLIC_AZURE_AD_TENANT_ID",
):
    value = os.environ.get(name, "").strip()
    if value:
        settings.append({"name": name, "value": value, "slotSetting": False})

with open(sys.argv[1], "w", encoding="utf-8") as handle:
    json.dump(settings, handle)
PY

az webapp config appsettings set \
  --name "$FRONTEND_APP_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --settings @"$FRONTEND_SETTINGS_JSON" \
  --output none

az webapp config container set \
  --name "$BACKEND_APP_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --container-image-name "$BACKEND_IMAGE" \
  --container-registry-url "https://$ACR_NAME.azurecr.io" \
  --output none

az webapp config container set \
  --name "$FRONTEND_APP_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --container-image-name "$FRONTEND_IMAGE" \
  --container-registry-url "https://$ACR_NAME.azurecr.io" \
  --output none

verify_health() {
  curl --fail --silent --show-error --retry 30 --retry-delay 10 --retry-all-errors \
    "$BACKEND_URL/api/health" > /dev/null
  curl --fail --silent --show-error --retry 30 --retry-delay 10 --retry-all-errors \
    "$FRONTEND_URL" > /dev/null
}

if ! verify_health; then
  echo 'Health check did not pass; restarting both web apps'
  az webapp restart --name "$BACKEND_APP_NAME" --resource-group "$RESOURCE_GROUP" --output none
  az webapp restart --name "$FRONTEND_APP_NAME" --resource-group "$RESOURCE_GROUP" --output none
  verify_health
fi

{
  echo "### Deployed images"
  echo ""
  echo "- commit: \`$DEPLOY_SHA\`"
  echo "- tag: \`$IMAGE_TAG\`"
  echo "- \`$BACKEND_IMAGE\`"
  echo "- \`$FRONTEND_IMAGE\`"
  echo "- backend: $BACKEND_URL"
  echo "- frontend: $FRONTEND_URL"
} >> "$GITHUB_STEP_SUMMARY"
