# Charlotte CI/CD

Charlotte lives outside the FO-AI GitHub org, but it follows the same CI/CD contract as every
FO-AI app (Nimbus, Benny). It calls the shared reusable workflows in the **public**
[`FO-AI/automation`](https://github.com/FO-AI/automation) repo directly, so there is no copy
of the shared pipeline logic in this repo. Read that repo's README once before starting; this
document covers only what is specific to Charlotte.

## Status

| Piece | State |
| --- | --- |
| `.github/workflows/ci.yml` | **Live.** Runs on every PR and every push to `main`. |
| `scripts/ci.sh` | **Live**, with starter checks (see below). Needs real tests. |
| `publish` job in `ci.yml` | **Wired, skipped.** It runs only once the `ACR_NAME` repository variable exists. |
| `scripts/publish.sh` | **Implemented.** Builds both images in ACR by commit SHA and proves digests. Still gated by `ACR_NAME`. |
| `.github/workflows/cd.yml` | **Wired, manual only.** `workflow_run` is commented out. |
| `scripts/cd.sh` | **Skeleton.** Validates inputs, then exits 1 with TODOs. |
| `scripts/docker-build-and-push.sh` | Old laptop deploy. **Still the way to ship** until `cd.sh` works. Delete it last. |

## How the pipeline fits together

```
PR ──► CI: checks/backend, checks/frontend ──► checks/Build backend, checks/Build frontend ──► verify
main ─► CI: (same) ──► verify ──► publish (scripts/publish.sh: build in ACR, tag = commit SHA)
                                      │
                                      ▼
        CD (workflow_run on green main CI) ──► reusable-azure-cd ──► scripts/cd.sh
            (dev environment, stale-main check, OIDC login)        (promote by digest, verify)
```

The contract gives this repo three scripts with one job each:

| Script | Does | Must not |
| --- | --- | --- |
| `scripts/ci.sh <check>` | Runs one named check (`backend` or `frontend`). Sets its own fake env so it runs the same on a laptop. | Touch Azure. Read secrets. |
| `scripts/publish.sh` | Builds `charlotte-backend:$IMAGE_TAG` and `charlotte-frontend:$IMAGE_TAG` in ACR and proves both resolve to digests. | Deploy. Tag `latest`. |
| `scripts/cd.sh` | Looks up those digests, applies settings, points both web apps at `image@sha256:…`, rechecks `main`, verifies health. | Build. Take a digest from its environment. |

Both workflows are pinned to the FO-AI automation commit that Nimbus and Benny use
(`4879ef3…`, the v2 interface). Only bump the pin in a PR, and bump both files together.

## Running checks locally

```bash
# backend (Python 3.11)
python -m pip install -r backend/requirements.txt
bash scripts/ci.sh backend

# frontend (Node 20, matching frontend/Dockerfile)
npm --prefix frontend ci
bash scripts/ci.sh frontend
```

What the checks do today:

- **backend**: imports `main` with fake settings and calls `GET /api/health` through FastAPI's
  `TestClient`. This catches broken imports and missing dependencies, and nothing else. The pip
  install (chromadb, grpcio, huggingface-hub) takes a few minutes on CI because nothing is
  cached. That's expected.
- **frontend**: `next lint`, then `next build` with placeholder `NEXT_PUBLIC_*` values. Lint
  warnings are allowed. Lint errors fail the check. Note that `next.config.js` sets
  `ignoreDuringBuilds`, so the build step never lints; `ci.sh` runs lint separately.
- **Build backend / Build frontend**: Docker builds of each Dockerfile. They never push.
  They run only after both checks pass.

`verify` is the single status check to require. It stays the same when checks are added or
renamed.

## Configuration inventory

Everything the old script read from the laptop's shell falls into one of three buckets. Nothing
secret goes in a repository variable, a workflow file, or `ci.sh`.

**Repository variables** (Settings → Secrets and variables → Actions → Variables). The `publish`
job runs without an environment, so it can read only repo-level values.

| Name | Value |
| --- | --- |
| `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID` | From the Azure setup below. |
| `NEXT_PUBLIC_API_BASE_URL` | `https://charlotte-backend.azurewebsites.net` |
| `NEXT_PUBLIC_AZURE_AD_CLIENT_ID`, `NEXT_PUBLIC_AZURE_AD_TENANT_ID` | Charlotte's Entra SPA client/tenant (public values; same as today's `AZURE_AD_*`). |
| `ACR_NAME` | `charlotteacr`. **Set this last**: it switches the `publish` job on. |

**`dev` environment variables** (Settings → Environments → `dev`). `cd.sh` reads these from
`DEPLOYMENT_VARS_JSON`.

| Name | Value |
| --- | --- |
| `RESOURCE_GROUP` | `rg-primary-unc-foit-charlotte-ai` |
| `ACR_NAME` | `charlotteacr` |
| `BACKEND_APP_NAME` / `FRONTEND_APP_NAME` | `charlotte-backend` / `charlotte-frontend` |
| `BACKEND_URL` / `FRONTEND_URL` | `https://charlotte-backend.azurewebsites.net` / the frontend URL |

**`dev` environment secret `API_ENV_FILE`**: one multi-line secret in `.env` format holding every
backend app setting the old script pushed with `az webapp config appsettings set`:
`AZURE_SEARCH_*`, `AZURE_AI_PROJECT_ENDPOINT`, `AZURE_AI_RESOURCE_ENDPOINT`, `AZURE_AD_*`
(including `AZURE_AD_CLIENT_SECRET` and `AZURE_AD_REDIRECT_URI`), `AZURE_AGENT_ID`,
`AZURE_OPENAI_KEY`, `SMALL_MODEL_NAME`, `AZURE_MASTER_SEARCH_INDEX`, `AZURE_STORAGE_*`,
`EDI_JSON_OUTPUT_CONTAINER`, `AZURE_MASTER_EDI_CONTAINER`, `AZURE_COSMOS_*`,
`AZURE_ALIGNRX_REPORTS_CONTAINER`, `AZURE_DI_*`. The frontend has no runtime secrets, so
`WEB_ENV_FILE` is not needed. `cd.sh` can set the frontend's non-secret app settings from the
repository variables above.

Charlotte already has `Production` and `Preview` environments from earlier experiments. The
FO-AI contract uses `dev`, so create `dev` and leave the other two alone.

## Azure setup (Om)

The intern needs only the resulting IDs. These steps need rights on the Charlotte subscription.

1. **App registration** (or user-assigned managed identity) for GitHub Actions. Its client ID
   becomes `AZURE_CLIENT_ID`.
2. **Two federated credentials** on it. Charlotte is a personal repo, so the subjects use the
   plain owner/name form, not the org form in Nimbus's comments:
   - `repo:omshewale30/charlotte:ref:refs/heads/main` (the `publish` job)
   - `repo:omshewale30/charlotte:environment:dev` (the `deploy` job)

   Issuer `https://token.actions.githubusercontent.com`, audience `api://AzureADTokenExchange`.
3. **Roles** for that identity:
   - `AcrPush` on `charlotteacr` (publish builds and pushes; deploy reads digests).
   - `Website Contributor` on `charlotte-backend` and `charlotte-frontend`, or on the
     resource group.
4. **Have the web apps pull with managed identity** instead of ACR admin credentials. The old
   script pulled admin creds with `az acr credential show`, and `cd.sh` should never handle a
   registry password. For each web app:
   ```bash
   az webapp identity assign -g rg-primary-unc-foit-charlotte-ai -n <app>
   az role assignment create --assignee <principalId> --role AcrPull \
     --scope $(az acr show -n charlotteacr --query id -o tsv)
   az webapp config set -g rg-primary-unc-foit-charlotte-ai -n <app> \
     --generic-configurations '{"acrUseManagedIdentityCreds": true}'
   ```
   Once both apps deploy this way, disable the ACR admin user.
5. Create the `dev` environment. Under *Deployment branches*, allow only `main`.

## Intern task list

Do these in order. Each one is a separate PR that must show green `verify`.

1. **Real backend tests.** Add `backend/requirements-dev.txt` with `pytest` and `ruff`. Add
   `-r backend/requirements-dev.txt` to the backend `install` string in `ci.yml`. Replace the
   smoke test in `ci.sh backend` with `ruff check .` and `pytest`. Start with route tests
   using `TestClient` and mock the Azure clients. Tests must not need real credentials.
2. **Frontend tests.** Optional but encouraged. Add a `test` script and call it from
   `ci.sh frontend`. Consider fixing the `react-hooks/exhaustive-deps` warnings.
3. **`scripts/publish.sh`.** Follow its TODOs. Test from a laptop with `az login` and
   `IMAGE_TAG=$(git rev-parse HEAD)`, then ask Om to set `ACR_NAME`. Merge, and confirm the
   `publish` job on `main` lists both digests in its summary. Finally, delete the
   `vars.ACR_NAME != ''` clause from `ci.yml`.
4. **`scripts/cd.sh`.** Follow its TODOs. Ask Om to create `API_ENV_FILE`. Run CD manually
   (Actions → CD → Run workflow) and confirm both apps serve the new digest and
   `/api/health` returns 200.
5. **Turn on automatic CD.** Uncomment `workflow_run` in `cd.yml`.
6. **Retire the old path.** Delete `scripts/docker-build-and-push.sh` and ask Om to disable
   the ACR admin user. Keep `azure-setup.sh` and `cleanup-azure.sh`; those are one-time infra
   scripts, not part of the pipeline.

## Where the old script's pieces go

| `docker-build-and-push.sh` did | Now |
| --- | --- |
| `docker buildx build --push` both images | `publish.sh` via `az acr build` |
| Tag `:$IMAGE_TAG` **and `:latest`** | `:<full commit SHA>` only; the contract forbids `latest`. |
| `az acr credential show` (admin user) | OIDC for CI; managed identity for the web apps' pull. |
| `az webapp config appsettings set` from local shell vars | `cd.sh`, reading `API_ENV_FILE` from the `dev` environment. |
| `az webapp config container set …:$IMAGE_TAG` | `cd.sh`, with `…@sha256:<digest>` looked up from ACR. |
| `az webapp restart` | `cd.sh`, only if needed, followed by a health check. |

## Rules of the road

- **Never** put a secret in `ci.yml`, `ci.sh`, a Docker build arg, or a repository variable.
- Reusable workflows stay SHA-pinned. Don't point them at `@main`.
- Branch protection (require `verify`, no direct pushes) needs GitHub Pro on a private personal
  repo. If it isn't available, treat "`verify` is green" as a manual merge rule.
- No `actionlint` in CI yet. Run it locally (`brew install actionlint`) before pushing workflow
  changes.
- Stuck? Compare against `FO-AI/nimbus` (`az acr build`, simplest) before inventing
  something new. The goal is that someone moving between repos finds the same three scripts
  doing the same three jobs.
