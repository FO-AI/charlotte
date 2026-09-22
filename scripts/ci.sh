#!/usr/bin/env bash
# Run one named CI check. No cloud access. Part of the FO-AI repository script
# contract (scripts/ci.sh, scripts/publish.sh, scripts/cd.sh); see the
# FO-AI/automation README and docs/CI-CD.md. Run after the selected check's
# dependencies are installed.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

frontend() (
  # Next.js inlines NEXT_PUBLIC_* at build time. Placeholders are enough to prove
  # the app compiles; publish.sh bakes in the real values.
  export NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
  export NEXT_PUBLIC_AZURE_AD_CLIENT_ID=00000000-0000-0000-0000-000000000000
  export NEXT_PUBLIC_AZURE_AD_TENANT_ID=00000000-0000-0000-0000-000000000000
  cd frontend
  npm run lint
  # TODO(intern): add `npm run test` once the frontend has tests.
  npm run build
)

backend() (
  # config/settings.py requires these at import time. Fake values, set here rather
  # than in the workflow so the check behaves identically on a laptop and in CI.
  # No Azure credentials involved: nothing below may reach a real service.
  for name in AZURE_SEARCH_ENDPOINT AZURE_AI_PROJECT_ENDPOINT AZURE_AI_RESOURCE_ENDPOINT; do
    export "$name=https://ci.invalid"
  done
  for name in AZURE_SEARCH_API_KEY AZURE_SEARCH_INDEX_NAME AZURE_MASTER_SEARCH_INDEX \
      AZURE_AD_TENANT_ID AZURE_AD_CLIENT_ID AZURE_AD_CLIENT_SECRET AZURE_AGENT_ID \
      AZURE_OPENAI_KEY AZURE_STORAGE_CONTAINER_NAME AZURE_STORAGE_ACCOUNT_NAME \
      AZURE_STORAGE_KEY AZURE_ALIGNRX_REPORTS_CONTAINER AZURE_MASTER_EDI_CONTAINER; do
    export "$name=ci-placeholder"
  done
  export AZURE_STORAGE_CONNECTION_STRING="DefaultEndpointsProtocol=https;AccountName=ci;AccountKey=Y2k=;EndpointSuffix=ci.invalid"
  cd backend
  # CI provides `python` with the install from ci.yml. On laptops, fall back to python3
  # when the shell's `python` is a different environment without ruff/pytest.
  py=python
  if ! python -c 'import ruff, pytest' >/dev/null 2>&1; then
    py=python3
  fi
  "$py" -m ruff check .
  "$py" -m pytest
)

case "${1:-}" in
  backend) backend ;;
  frontend) frontend ;;
  *) echo "Usage: bash scripts/ci.sh {backend|frontend}" >&2; exit 2 ;;
esac
