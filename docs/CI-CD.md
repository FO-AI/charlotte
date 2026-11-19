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
| `scripts/ci.sh` | **Live.** Backend ruff+pytest; frontend lint (`--max-warnings 0`), Playwright e2e, then build. |
| `publish` job in `ci.yml` | **Live.** Runs on every push to `main` after `verify`. |
| `scripts/publish.sh` | **Implemented.** Builds both images in ACR by commit SHA and proves digests. |
| `.github/workflows/cd.yml` | **Wired, manual only.** `workflow_run` is commented out. |
| `scripts/cd.sh` | **Implemented.** Promotes both images by digest and health-checks. CD stays manual until task 5. |
| `scripts/docker-build-and-push.sh` | Old laptop deploy helper for the App Service path. Keep until the old path is retired. |

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
| `scripts/publish.sh` | Builds `charlotte-backend:$IMAGE_TAG` and `charlotte-frontend:$IMAGE_TAG` in ACR in parallel and proves both resolve to digests. | Deploy. Tag `latest`. |
| `scripts/cd.sh` | Looks up those digests, rechecks `main`, points both Container Apps at `image@sha256:…`, verifies health. | Build. Take a digest from its environment. Change app settings or secrets. |

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
- **frontend**: `eslint` with `--max-warnings 0`, then Playwright e2e (`npm run test:e2e`),
  then `next build` with placeholder `NEXT_PUBLIC_*` values. Any lint warning fails the check.
  Note that `next.config.js` sets `ignoreDuringBuilds`, so the build step never lints;
  `ci.sh` runs lint separately. Chromium is installed in the workflow frontend install step.
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
| `NEXT_PUBLIC_API_BASE_URL` | Backend public URL, baked into the frontend image at build time. |
| `NEXT_PUBLIC_AZURE_AD_CLIENT_ID`, `NEXT_PUBLIC_AZURE_AD_TENANT_ID` | Charlotte's Entra SPA client/tenant (public values; same as today's `AZURE_AD_*`). |
| `ACR_NAME` | `charlotteacr`. **Set this last**: it switches the `publish` job on. |

**`dev` environment variables** (Settings → Environments → `dev`). `cd.sh` reads these from
`DEPLOYMENT_VARS_JSON`.

| Name | Value |
| --- | --- |
| `RESOURCE_GROUP` | `rg-primary-unc-foit-charlotte-ai` |
| `ACR_NAME` | `charlotteacr` |
| `BACKEND_APP_NAME` / `FRONTEND_APP_NAME` | `charlotte-backend` / `charlotte-frontend` |
| `BACKEND_URL` / `FRONTEND_URL` | Backend and frontend Container App URLs used for health checks. |

Container App environment variables and secrets live on `charlotte-backend` and
`charlotte-frontend`, not in the deploy pipeline. Change nonsecret values with
`az containerapp update --set-env-vars`; change secret values with `az containerapp secret set`
and keep secret-backed variables as `secretref:` references. `cd.sh` ignores `API_ENV_FILE` and
`WEB_ENV_FILE` even though the shared wrapper still passes them.

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
   - Container Apps update rights on `charlotte-backend` and `charlotte-frontend`, or on the
     resource group.
4. **Container App registry pull is app-owned.** The Container Apps already have registry access
   configured through their Container Apps registry secret. `cd.sh` should never handle a
   registry password.
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
4. **`scripts/cd.sh`.** Follow its TODOs. Run CD manually (Actions → CD → Run workflow) and
   confirm both Container Apps serve the new digest and `/api/health` returns 200.
5. **Turn on automatic CD.** Uncomment `workflow_run` in `cd.yml`.
6. **Retire the old path.** Delete `scripts/docker-build-and-push.sh` and ask Om to disable
   the ACR admin user. Keep `azure-setup.sh` and `cleanup-azure.sh`; those are one-time infra
   scripts, not part of the pipeline.

## Where the old script's pieces go

| `docker-build-and-push.sh` did | Now |
| --- | --- |
| `docker buildx build --push` both images | `publish.sh` via `az acr build` |
| Tag `:$IMAGE_TAG` **and `:latest`** | `:<full commit SHA>` only; the contract forbids `latest`. |
| `az acr credential show` (admin user) | OIDC for CI; Container Apps keep their own registry pull configuration. |
| `az webapp config appsettings set` from local shell vars | Container App env vars and secrets, managed outside the pipeline with `az containerapp update --set-env-vars` and `az containerapp secret set`. |
| `az webapp config container set …:$IMAGE_TAG` | `cd.sh`, with `az containerapp update --image …@sha256:<digest>` looked up from ACR. |
| `az webapp restart` | No deploy restart fallback. `cd.sh` health-checks and prints revision diagnostics on failure. |

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
