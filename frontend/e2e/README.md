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

CI: not wired into `scripts/ci.sh` yet — keep backend CI green; run this locally before merging review-UI changes.
