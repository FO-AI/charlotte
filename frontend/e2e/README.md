# Outside scholarships Playwright e2e

Stubbed API review flow (no real auth or backend required). The harness only activates
under `next dev` when `NEXT_PUBLIC_ENABLE_E2E_HARNESS=1` (Playwright sets this). Production
builds never skip MSAL even if that env var were set at build time.

```bash
cd frontend
npm install
npx playwright install chromium
npm run test:e2e:outside-scholarships
```

Artifacts (trace, screenshots, HTML report) land under `e2e/artifacts/`.

CI: `bash scripts/ci.sh frontend` runs `npm run test:e2e` (all tests under `e2e/`) after lint
and before `next build`. The GitHub Actions frontend install step installs Chromium with
`npx --prefix frontend playwright install --with-deps chromium`. Locally, install Chromium
yourself (`npx playwright install chromium`) before running `bash scripts/ci.sh frontend`.
