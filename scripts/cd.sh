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
# STATUS: skeleton. Replaces the deploy half of scripts/docker-build-and-push.sh.
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
if [[ ! "$IMAGE_TAG" =~ ^[0-9a-f]{40}$ ]]; then
  echo '::error::IMAGE_TAG must be a full commit SHA; publish.sh tags images by it'
  exit 1
fi

# TODO(intern) 1. Read deployment settings. Copy Nimbus's DEPLOYMENT_VARS_JSON loop for:
#   RESOURCE_GROUP ACR_NAME BACKEND_APP_NAME FRONTEND_APP_NAME BACKEND_URL FRONTEND_URL
#   and fail with ::error:: naming any that are missing.
#
# TODO(intern) 2. Write API_ENV_FILE to "$RUNNER_TEMP/charlotte-backend.env" with umask 077,
#   `unset API_ENV_FILE`, and add `trap cleanup EXIT` that deletes the file. It holds every
#   backend app setting the old script pushed (keys, connection strings, client secret).
#
# TODO(intern) 3. Validate targets exist (read-only):
#   az webapp show --name "$BACKEND_APP_NAME"  --resource-group "$RESOURCE_GROUP" --output none
#   az webapp show --name "$FRONTEND_APP_NAME" --resource-group "$RESOURCE_GROUP" --output none
#
# TODO(intern) 4. Resolve digests from ACR (never from the environment):
#   az acr repository show --name "$ACR_NAME" --image "charlotte-backend:${IMAGE_TAG}" \
#     --query digest -o tsv            # must match ^sha256:[0-9a-f]{64}$
#   BACKEND_IMAGE="$ACR_NAME.azurecr.io/charlotte-backend@$BACKEND_DIGEST"  (same for frontend)
#
# TODO(intern) 5. Recheck main immediately before the first change to Azure:
#   main_sha="$(gh api "repos/${GITHUB_REPOSITORY}/git/ref/heads/main" --jq '.object.sha')"
#   [[ "$DEPLOY_SHA" == "$main_sha" ]] || { echo '::error::Refusing stale deployment'; exit 1; }
#
# TODO(intern) 6. Apply backend app settings from the env file:
#   az webapp config appsettings set --name "$BACKEND_APP_NAME" \
#     --resource-group "$RESOURCE_GROUP" --settings @<json file built from the env file>
#   (use a file, not argv, so secrets never appear in the process list or logs)
#
# TODO(intern) 7. Point each web app at its image BY DIGEST. The web apps pull with their
#   managed identity (docs/CI-CD.md, Azure setup), so pass no registry username/password:
#   az webapp config container set --name "$BACKEND_APP_NAME" \
#     --resource-group "$RESOURCE_GROUP" --container-image-name "$BACKEND_IMAGE" \
#     --container-registry-url "https://$ACR_NAME.azurecr.io"
#   (then the same for the frontend; restart both only if the change does not take effect)
#
# TODO(intern) 8. Verify:
#   curl --fail --silent --show-error --retry 30 --retry-delay 10 --retry-all-errors \
#     "$BACKEND_URL/api/health" > /dev/null
#   curl ... "$FRONTEND_URL" > /dev/null
#
# TODO(intern) 9. Append commit, both image@digest references, and both URLs to
#   "$GITHUB_STEP_SUMMARY".

echo '::error::scripts/cd.sh is not implemented yet; see the TODOs in this file and docs/CI-CD.md'
exit 1
