#!/usr/bin/env bash
# Build every Charlotte image for $IMAGE_TAG in ACR as charlotte-<service>:$IMAGE_TAG and
# prove both pushed. Publishes only; it never touches a web app. Promotion is scripts/cd.sh.
#
# Part of the FO-AI repository script contract (scripts/ci.sh, scripts/publish.sh,
# scripts/cd.sh); see the FO-AI/automation README and docs/CI-CD.md.
#
# Needs: az signed in (OIDC in CI, `az login` on a laptop) with AcrPush on ACR_NAME,
#        ACR_NAME, IMAGE_TAG (a full commit SHA), and the three NEXT_PUBLIC_* values below.
#        Next.js inlines NEXT_PUBLIC_* at `next build`, so they must be baked into the
#        frontend image. None is a secret (a URL and client/tenant IDs); in CI they are
#        repository variables, because this job runs outside the dev environment.
#
# Must not: deploy, or tag anything `latest`.
#
# STATUS: implemented. Replaces the build half of scripts/docker-build-and-push.sh.
# Reference implementation: FO-AI/nimbus scripts/publish.sh (same `az acr build` shape).
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

for name in ACR_NAME IMAGE_TAG \
    NEXT_PUBLIC_API_BASE_URL NEXT_PUBLIC_AZURE_AD_CLIENT_ID NEXT_PUBLIC_AZURE_AD_TENANT_ID; do
  if [[ -z "${!name:-}" ]]; then
    printf '::error::Missing publish setting: %s (set it as a repository variable)\n' "$name"
    exit 1
  fi
done
if [[ ! "$IMAGE_TAG" =~ ^[0-9a-f]{40}$ ]]; then
  echo '::error::IMAGE_TAG must be a full commit SHA; cd.sh looks images up by that tag'
  exit 1
fi

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

az acr build --registry "$ACR_NAME" --image "charlotte-backend:${IMAGE_TAG}" backend

az acr build --registry "$ACR_NAME" --image "charlotte-frontend:${IMAGE_TAG}" \
  --build-arg "NEXT_PUBLIC_API_BASE_URL=${NEXT_PUBLIC_API_BASE_URL}" \
  --build-arg "NEXT_PUBLIC_AZURE_AD_CLIENT_ID=${NEXT_PUBLIC_AZURE_AD_CLIENT_ID}" \
  --build-arg "NEXT_PUBLIC_AZURE_AD_TENANT_ID=${NEXT_PUBLIC_AZURE_AD_TENANT_ID}" \
  frontend

backend_digest="$(digest_for backend)"
frontend_digest="$(digest_for frontend)"
backend_ref="${ACR_NAME}.azurecr.io/charlotte-backend@${backend_digest}"
frontend_ref="${ACR_NAME}.azurecr.io/charlotte-frontend@${frontend_digest}"

{
  echo "### Published images"
  echo ""
  echo "- \`${backend_ref}\`"
  echo "- \`${frontend_ref}\`"
}

if [[ -n "${GITHUB_STEP_SUMMARY:-}" ]]; then
  {
    echo "### Published images"
    echo ""
    echo "- \`${backend_ref}\`"
    echo "- \`${frontend_ref}\`"
  } >> "$GITHUB_STEP_SUMMARY"
fi
