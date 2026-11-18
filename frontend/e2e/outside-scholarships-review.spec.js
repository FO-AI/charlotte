const { test, expect } = require('@playwright/test');
const fs = require('fs');
const path = require('path');

const preview = JSON.parse(
  fs.readFileSync(path.join(__dirname, 'fixtures', 'preview.json'), 'utf8')
);

const FIXED_PID = '123456789';
const AD_NAME = 'Example, Alex';
const SUPPORTING_RESOLUTION = /Open the Supporting page\. If it is a check/i;
const EXTRACTION_RESOLUTION = /Check each field against the images/i;
const BAD_PID_VERIFY_GUIDANCE =
  'Fix the PID first. Mark verified stays disabled until every PID has nine digits.';
const VERIFY_INVALID_AMOUNT_MESSAGE = 'Enter a valid amount before marking verified.';
const VERIFY_PID_LOOKUP_MESSAGE = 'Looking up the changed PID before marking verified.';

function buildExtractionFailedPreview(checkOverrides = {}) {
  return {
    ...preview,
    checks: [
      {
        ...preview.checks[0],
        provider: 'Example Foundation',
        amount: '250.00',
        name: 'Alex Example',
        supporting_looks_like_check: false,
        extraction_failed: true,
        pids: [{ pid: FIXED_PID, active_directory: { status: 'found', name: AD_NAME } }],
        ...checkOverrides,
      },
    ],
  };
}

async function stubReviewApis(page, previewBody, options = {}) {
  const lookupByPid =
    options.lookupByPid ||
    ((pid) =>
      pid === FIXED_PID
        ? { status: 'found', name: AD_NAME }
        : { status: 'not_found', name: null });

  await page.route('**/api/banking/outside-scholarships/active-directory-names', async (route) => {
    const body = route.request().postDataJSON();
    const pids = Array.isArray(body?.pids) ? body.pids : [];
    if (options.onLookup) {
      options.onLookup(pids);
    }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        pids: pids.map((pid) => ({
          pid,
          active_directory: lookupByPid(pid),
        })),
      }),
    });
  });

  await page.route('**/api/banking/outside-scholarships/export', async (route) => {
    if (options.onExport) {
      options.onExport(route.request().postDataJSON());
    }
    await route.fulfill({
      status: 200,
      contentType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      headers: {
        'content-disposition': 'attachment; filename="outside_scholarships_reviewed.xlsx"',
      },
      body: Buffer.from('PK-fake-xlsx'),
    });
  });

  const jobId = 'e2e-outside-scholarships-job';
  let jobPolls = 0;
  await page.route('**/api/banking/outside-scholarships/jobs/**', async (route) => {
    if (options.onJobPoll) {
      options.onJobPoll();
    }
    jobPolls += 1;
    // First poll streams a real progress update; later polls return the preview.
    if (jobPolls === 1 && options.progressBody) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(options.progressBody),
      });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(previewBody),
    });
  });

  await page.route('**/api/banking/outside-scholarships', async (route) => {
    if (route.request().method() !== 'POST') {
      await route.continue();
      return;
    }
    // Exclude nested routes handled above
    const url = route.request().url();
    if (url.includes('active-directory-names') || url.includes('/export') || url.includes('/jobs/')) {
      await route.continue();
      return;
    }
    await route.fulfill({
      status: 202,
      contentType: 'application/json',
      body: JSON.stringify({ job_id: jobId, status: 'processing' }),
    });
  });
}

async function uploadAndOpenReview(page) {
  await page.goto('/e2e/outside-scholarships');

  await expect(page.getByRole('heading', { name: /Upload Outside Scholarship Checks/i })).toBeVisible();

  const pdfBytes = Buffer.from(
    '%PDF-1.1\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n',
    'utf8'
  );
  await page.setInputFiles('input[type="file"]', {
    name: 'sample-checks.pdf',
    mimeType: 'application/pdf',
    buffer: pdfBytes,
  });

  await page.getByRole('button', { name: 'Upload Check PDF' }).click();

  await expect(page.getByRole('dialog', { name: 'Review outside scholarship checks' })).toBeVisible({
    timeout: 15_000,
  });
}

test.describe('Outside scholarships review flow', () => {
  test('upload polls the extraction job until the preview is ready', async ({ page }) => {
    let polls = 0;
    await stubReviewApis(page, preview, {
      onJobPoll: () => { polls += 1; },
      progressBody: {
        job_id: 'e2e-outside-scholarships-job',
        status: 'processing',
        stage: 'extracting_checks',
        message: 'Reading check 1 of 2…',
        checks_total: 2,
        checks_done: 1,
      },
    });

    await page.goto('/e2e/outside-scholarships');
    const pdfBytes = Buffer.from(
      '%PDF-1.1\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n',
      'utf8'
    );
    await page.setInputFiles('input[type="file"]', {
      name: 'sample-checks.pdf',
      mimeType: 'application/pdf',
      buffer: pdfBytes,
    });
    await page.getByRole('button', { name: 'Upload Check PDF' }).click();

    await expect(page.getByText('Reading check 1 of 2…')).toBeVisible({ timeout: 10_000 });
    await expect(page.getByRole('dialog', { name: 'Review outside scholarship checks' })).toBeVisible({
      timeout: 15_000,
    });
    expect(polls).toBeGreaterThan(0);
  });

  test('upload → fix PID → AD name → export', async ({ page }) => {
    await stubReviewApis(page, preview);
    await uploadAndOpenReview(page);

    await expect(page.getByText(/1 of 1 left/i).first()).toBeVisible();
    await expect(page.getByRole('button', { name: 'Export Excel' })).toBeDisabled();
    await expect(page.getByText(/Bad PID/i).first()).toBeVisible();

    const pidInput = page.getByLabel('PID for check 1');
    await expect(pidInput).toHaveValue('12345');
    await pidInput.fill(FIXED_PID);
    await pidInput.press('Enter');

    await expect(page.getByText(AD_NAME, { exact: true })).toBeVisible({ timeout: 10_000 });
    await expect(page.getByText(/Missing provider/i).first()).toBeVisible();

    // Resolve remaining flag via Mark verified (workflow aid — export does not re-validate).
    const verifyButton = page.getByRole('button', { name: 'Mark verified' });
    await verifyButton.scrollIntoViewIfNeeded();
    await verifyButton.click();
    await expect(page.getByRole('button', { name: 'Undo' })).toBeVisible({ timeout: 10_000 });
    await expect(page.getByText(/0 of 1 left/i).first()).toBeVisible();

    await expect(page.getByRole('button', { name: 'Export Excel' })).toBeEnabled();

    const downloadPromise = page.waitForEvent('download');
    await page.getByRole('button', { name: 'Export Excel' }).click();
    const download = await downloadPromise;
    expect(download.suggestedFilename()).toMatch(/outside_scholarships/i);

    // After export the review closes; capture the harness page (or last frame via video/trace).
    const artifactsDir = path.join(__dirname, 'artifacts');
    fs.mkdirSync(artifactsDir, { recursive: true });
    await page.screenshot({ path: path.join(artifactsDir, 'outside-scholarships-after-export.png'), fullPage: true });
  });

  // Ways this could fail: keystrokes in the blank PID box are dropped; focus leaves the box
  // after the first keystroke; removing the last PID leaves a box that ignores typing again;
  // a second blank row appears; the PID is typed but never looked up, so Export stays disabled.
  test('check with no PIDs → type PID → AD name → export', async ({ page }) => {
    const noPidPreview = {
      ...preview,
      checks: [{ ...preview.checks[0], provider: 'Example Foundation', pids: [] }],
    };
    await stubReviewApis(page, noPidPreview);
    await uploadAndOpenReview(page);

    const pidInputs = page.getByLabel('PID for check 1');
    await expect(pidInputs).toHaveCount(1);
    await expect(pidInputs).toHaveValue('');
    await expect(page.getByRole('button', { name: 'Export Excel' })).toBeDisabled();

    const searchButton = page.getByRole('button', {
      name: 'Search Active Directory for PID on check 1',
    });

    await pidInputs.click();
    await pidInputs.pressSequentially(FIXED_PID);
    await expect(pidInputs).toHaveValue(FIXED_PID);
    await expect(pidInputs).toBeFocused();
    await searchButton.click();
    await expect(page.getByText(AD_NAME, { exact: true })).toBeVisible({ timeout: 10_000 });

    // Clearing the field resets AD; search again after retyping.
    await pidInputs.fill('');
    await expect(pidInputs).toHaveValue('');
    await expect(page.getByText(AD_NAME, { exact: true })).toBeHidden();

    await pidInputs.click();
    await pidInputs.pressSequentially(FIXED_PID);
    await expect(pidInputs).toHaveValue(FIXED_PID);
    await searchButton.click();
    await expect(page.getByText(AD_NAME, { exact: true })).toBeVisible({ timeout: 10_000 });
    await expect(pidInputs).toHaveCount(1);

    await expect(page.getByText(/0 of 1 left/i).first()).toBeVisible();
    await expect(page.getByRole('button', { name: 'Export Excel' })).toBeEnabled();

    const artifactsDir = path.join(__dirname, 'artifacts');
    fs.mkdirSync(artifactsDir, { recursive: true });
    await page.screenshot({ path: path.join(artifactsDir, 'outside-scholarships-no-pid-typed.png'), fullPage: true });

    const downloadPromise = page.waitForEvent('download');
    await page.getByRole('button', { name: 'Export Excel' }).click();
    const download = await downloadPromise;
    expect(download.suggestedFilename()).toMatch(/outside_scholarships/i);
  });

  test('8-digit PID keeps Mark verified and Export Excel disabled', async ({ page }) => {
    const eightDigitPreview = {
      ...preview,
      checks: [
        {
          ...preview.checks[0],
          provider: 'Example Foundation',
          pids: [{ pid: '12345678', active_directory: { status: 'not_found', name: null } }],
        },
      ],
    };
    await stubReviewApis(page, eightDigitPreview);
    await uploadAndOpenReview(page);

    await expect(page.getByText(/Bad PID/i).first()).toBeVisible();
    await expect(page.getByRole('button', { name: 'Mark verified' })).toBeDisabled();
    await expect(page.getByRole('button', { name: 'Export Excel' })).toBeDisabled();
    await expect(page.getByText(/Bad PID — fix or clear before export/i)).toBeVisible();

    const pidInput = page.getByLabel('PID for check 1');
    await pidInput.fill('1234567');
    await expect(pidInput).toHaveValue('1234567');
    await expect(page.getByRole('button', { name: 'Mark verified' })).toBeDisabled();
    await expect(page.getByRole('button', { name: 'Export Excel' })).toBeDisabled();
  });

  test('multi-PID check requires review until Mark verified', async ({ page }) => {
    const multiPidPreview = {
      ...preview,
      checks: [
        {
          ...preview.checks[0],
          provider: 'Example Foundation',
          pids: [
            { pid: FIXED_PID, active_directory: { status: 'found', name: AD_NAME } },
            { pid: '987654321', active_directory: { status: 'found', name: AD_NAME } },
          ],
        },
      ],
    };
    await stubReviewApis(page, multiPidPreview);
    await uploadAndOpenReview(page);

    await expect(page.getByText(/Multiple PIDs/i).first()).toBeVisible();
    await expect(page.getByRole('button', { name: 'Export Excel' })).toBeDisabled();

    const verifyButton = page.getByRole('button', { name: 'Mark verified' });
    await expect(verifyButton).toBeEnabled();
    await verifyButton.click();

    await expect(page.getByRole('button', { name: 'Undo' })).toBeVisible();
    await expect(page.getByText(/0 of 1 left/i).first()).toBeVisible();
    await expect(page.getByRole('button', { name: 'Export Excel' })).toBeEnabled();

    const artifactsDir = path.join(__dirname, 'artifacts');
    fs.mkdirSync(artifactsDir, { recursive: true });
    await page.screenshot({ path: path.join(artifactsDir, 'outside-scholarships-multi-pid.png'), fullPage: true });
  });

  // Om #55: supporting page that looks like a check is flag-only — export blocked until Mark verified.
  test('supporting looks like check requires review until Mark verified', async ({ page }) => {
    const image = preview.checks[0].front_image;
    const supportingLooksLikeCheckPreview = {
      ...preview,
      checks: [
        {
          ...preview.checks[0],
          provider: 'Example Foundation',
          amount: '250.00',
          name: 'Alex Example',
          supporting_pages: [2],
          supporting_images: [image],
          supporting_looks_like_check: true,
          extraction_failed: false,
          pids: [{ pid: FIXED_PID, active_directory: { status: 'found', name: AD_NAME } }],
        },
      ],
    };
    await stubReviewApis(page, supportingLooksLikeCheckPreview);
    await uploadAndOpenReview(page);

    await expect(page.getByText(/Supporting looks like check/i).first()).toBeVisible();
    await expect(page.getByText(/1 of 1 left/i).first()).toBeVisible();
    await expect(page.getByRole('button', { name: 'Export Excel' })).toBeDisabled();

    const verifyButton = page.getByRole('button', { name: 'Mark verified' });
    await expect(verifyButton).toBeEnabled();

    // How to resolve is shown on the page (not only in a hover tooltip) and points at Mark verified.
    const resolutionText = SUPPORTING_RESOLUTION;
    await expect(page.getByText(resolutionText)).toBeVisible();
    const needsReviewBox = page.getByRole('status').filter({ hasText: 'Needs review' });
    await expect(needsReviewBox).toContainText('Supporting looks like check');
    await expect(needsReviewBox).toContainText(resolutionText);
    await expect(page.getByText('Supporting looks like check', { exact: true })).toHaveCount(1);
    await expect(verifyButton).toHaveAccessibleDescription(resolutionText);
    await expect(verifyButton).toHaveAttribute('data-emphasis', 'resolve-flag');

    const artifactsDir = path.join(__dirname, 'artifacts');
    fs.mkdirSync(artifactsDir, { recursive: true });
    await page.screenshot({
      path: path.join(artifactsDir, 'outside-scholarships-supporting-looks-like-check-merged-box.png'),
      fullPage: true,
    });
    // The review panel scrolls on its own, so capture the emphasized button separately.
    await verifyButton.scrollIntoViewIfNeeded();
    await page.screenshot({
      path: path.join(artifactsDir, 'outside-scholarships-supporting-looks-like-check-verify-button.png'),
    });

    await verifyButton.click();

    const undoButton = page.getByRole('button', { name: 'Undo' });
    await expect(undoButton).toBeVisible();
    await expect(undoButton).not.toHaveAttribute('data-emphasis', 'resolve-flag');
    await expect(page.getByText(resolutionText)).toBeHidden();
    await expect(page.getByText(/0 of 1 left/i).first()).toBeVisible();
    await expect(page.getByRole('button', { name: 'Export Excel' })).toBeEnabled();

    await page.screenshot({
      path: path.join(artifactsDir, 'outside-scholarships-supporting-looks-like-check.png'),
      fullPage: true,
    });
  });

  test('award-letter supporting page does not require supporting-check review', async ({ page }) => {
    const image = preview.checks[0].front_image;
    const awardLetterPreview = {
      ...preview,
      checks: [
        {
          ...preview.checks[0],
          provider: 'Example Foundation',
          amount: '250.00',
          check_number: '1001',
          name: 'Alex Example',
          supporting_pages: [2],
          supporting_images: [image],
          supporting_looks_like_check: false,
          extraction_failed: false,
          pids: [{ pid: FIXED_PID, active_directory: { status: 'found', name: AD_NAME } }],
        },
      ],
    };
    await stubReviewApis(page, awardLetterPreview);
    await uploadAndOpenReview(page);

    await expect(page.getByText(/Supporting looks like check/i)).toBeHidden();
    await expect(page.getByRole('status').filter({ hasText: 'Needs review' })).toHaveCount(0);
    await expect(page.getByText(/0 of 1 left/i).first()).toBeVisible();
    await expect(page.getByRole('button', { name: 'Export Excel' })).toBeEnabled();

    const artifactsDir = path.join(__dirname, 'artifacts');
    fs.mkdirSync(artifactsDir, { recursive: true });
    await page.screenshot({
      path: path.join(artifactsDir, 'outside-scholarships-award-letter-supporting-no-review.png'),
      fullPage: true,
    });
  });

  // Om #55: per-check extraction failure is flag-only — other checks OK; this one needs Mark verified.
  test('extraction failed requires review until Mark verified', async ({ page }) => {
    const extractionFailedPreview = buildExtractionFailedPreview();
    await stubReviewApis(page, extractionFailedPreview);
    await uploadAndOpenReview(page);

    await expect(page.getByText(/Extraction failed/i).first()).toBeVisible();
    await expect(page.getByText(/1 of 1 left/i).first()).toBeVisible();
    await expect(page.getByRole('button', { name: 'Export Excel' })).toBeDisabled();

    const verifyButton = page.getByRole('button', { name: 'Mark verified' });
    await expect(verifyButton).toBeEnabled();

    const resolutionText = EXTRACTION_RESOLUTION;
    await expect(page.getByText(resolutionText)).toBeVisible();
    await expect(verifyButton).toHaveAccessibleDescription(resolutionText);
    await expect(verifyButton).toHaveAttribute('data-emphasis', 'resolve-flag');

    await verifyButton.click();

    await expect(page.getByRole('button', { name: 'Undo' })).toBeVisible();
    await expect(page.getByText(resolutionText)).toBeHidden();
    await expect(page.getByText(/0 of 1 left/i).first()).toBeVisible();
    await expect(page.getByRole('button', { name: 'Export Excel' })).toBeEnabled();

    const artifactsDir = path.join(__dirname, 'artifacts');
    fs.mkdirSync(artifactsDir, { recursive: true });
    await page.screenshot({
      path: path.join(artifactsDir, 'outside-scholarships-extraction-failed.png'),
      fullPage: true,
    });
  });

  test('Mark verified commits an amount draft on a blank-provider check before export', async ({ page }) => {
    let exportBody = null;
    const extractionFailedPreview = buildExtractionFailedPreview({ provider: '' });
    await stubReviewApis(page, extractionFailedPreview, {
      onExport: (body) => {
        exportBody = body;
      },
    });
    await uploadAndOpenReview(page);

    const amountInput = page.getByLabel('Amount for check 1');
    await amountInput.fill('999.00');
    await expect(amountInput).toHaveValue('999.00');

    const verifyButton = page.getByRole('button', { name: 'Mark verified' });
    await expect(verifyButton).toBeEnabled();
    await verifyButton.click();

    await expect(page.getByRole('button', { name: 'Undo' })).toBeVisible();
    await expect(page.getByText(/0 of 1 left/i).first()).toBeVisible();
    await expect(page.getByRole('button', { name: 'Export Excel' })).toBeEnabled();

    const downloadPromise = page.waitForEvent('download');
    await page.getByRole('button', { name: 'Export Excel' }).click();
    await downloadPromise;

    await expect.poll(() => exportBody).not.toBeNull();
    expect(exportBody.checks[0].reviewed.amount).toBe('999.00');
    expect(exportBody.checks[0].reviewed.provider).toBe('');
    expect(exportBody.checks[0].verified).toBe(true);
  });

  test('Mark verified refuses a non-numeric amount draft with a message that clears after fixing', async ({ page }) => {
    const extractionFailedPreview = buildExtractionFailedPreview();
    await stubReviewApis(page, extractionFailedPreview);
    await uploadAndOpenReview(page);

    const amountInput = page.getByLabel('Amount for check 1');
    await amountInput.fill('abc');
    await expect(amountInput).toHaveValue('abc');

    const verifyButton = page.getByRole('button', { name: 'Mark verified' });
    await expect(verifyButton).toBeEnabled();
    await verifyButton.click();

    await expect(page.getByText(VERIFY_INVALID_AMOUNT_MESSAGE).first()).toBeVisible();
    await expect(page.getByRole('button', { name: 'Undo' })).toHaveCount(0);
    await expect(page.getByRole('button', { name: 'Mark verified' })).toBeVisible();
    await expect(amountInput).toHaveValue('abc');
    await expect(page.getByText(/Missing amount/i).first()).toBeVisible();
    await expect(page.getByText(/1 of 1 left/i).first()).toBeVisible();
    await expect(page.getByRole('button', { name: 'Export Excel' })).toBeDisabled();

    await amountInput.fill('999.00');
    await verifyButton.click();

    await expect(page.getByRole('button', { name: 'Undo' })).toBeVisible();
    await expect(page.getByText(VERIFY_INVALID_AMOUNT_MESSAGE)).toHaveCount(0);
    await expect(page.getByRole('button', { name: 'Export Excel' })).toBeEnabled();
  });

  test('Mark verified commits a changed PID draft, looks it up, and waits for a second click', async ({ page }) => {
    let exportBody = null;
    const lookupRequests = [];
    const changedPid = '987654321';
    const extractionFailedPreview = buildExtractionFailedPreview({
      pids: [{ pid: changedPid, active_directory: { status: 'found', name: AD_NAME } }],
    });
    await stubReviewApis(page, extractionFailedPreview, {
      onLookup: (pids) => {
        lookupRequests.push(...pids);
      },
      onExport: (body) => {
        exportBody = body;
      },
    });
    await uploadAndOpenReview(page);

    const pidInput = page.getByLabel('PID for check 1');
    await expect(pidInput).toHaveValue(changedPid);
    await pidInput.fill(FIXED_PID);

    const verifyButton = page.getByRole('button', { name: 'Mark verified' });
    await verifyButton.click();

    await expect(page.getByText(VERIFY_PID_LOOKUP_MESSAGE).first()).toBeVisible();
    await expect.poll(() => lookupRequests).toContain(FIXED_PID);
    await expect(page.getByRole('button', { name: 'Undo' })).toHaveCount(0);
    await expect(page.getByText(AD_NAME, { exact: true })).toBeVisible({ timeout: 10_000 });

    await verifyButton.click();
    await expect(page.getByRole('button', { name: 'Undo' })).toBeVisible();

    const downloadPromise = page.waitForEvent('download');
    await page.getByRole('button', { name: 'Export Excel' }).click();
    await downloadPromise;

    await expect.poll(() => exportBody).not.toBeNull();
    expect(exportBody.checks[0].reviewed.pids[0].pid).toBe(FIXED_PID);
    expect(exportBody.checks[0].reviewed.pids[0].active_directory.name).toBe(AD_NAME);
    expect(exportBody.checks[0].verified).toBe(true);
  });

  test('Tab from amount to Mark verified keeps the typed value', async ({ page }) => {
    let exportBody = null;
    await stubReviewApis(page, buildExtractionFailedPreview(), {
      onExport: (body) => {
        exportBody = body;
      },
    });
    await uploadAndOpenReview(page);

    const amountInput = page.getByLabel('Amount for check 1');
    await amountInput.click();
    await amountInput.fill('777.00');
    await expect(amountInput).toHaveValue('777.00');

    const verifyButton = page.getByRole('button', { name: 'Mark verified' });
    for (let i = 0; i < 8; i += 1) {
      await page.keyboard.press('Tab');
      if (await verifyButton.evaluate((element) => document.activeElement === element)) break;
    }
    await expect(verifyButton).toBeFocused();
    await page.keyboard.press('Space');

    await expect(page.getByRole('button', { name: 'Undo' })).toBeVisible();
    const downloadPromise = page.waitForEvent('download');
    await page.getByRole('button', { name: 'Export Excel' }).click();
    await downloadPromise;

    await expect.poll(() => exportBody).not.toBeNull();
    expect(exportBody.checks[0].reviewed.amount).toBe('777.00');
    expect(exportBody.checks[0].verified).toBe(true);
  });

  test('Escape reverts an amount draft', async ({ page }) => {
    await stubReviewApis(page, buildExtractionFailedPreview());
    await uploadAndOpenReview(page);

    const amountInput = page.getByLabel('Amount for check 1');
    await amountInput.fill('888.00');
    await expect(amountInput).toHaveValue('888.00');
    await amountInput.press('Escape');
    await expect(amountInput).toHaveValue('250.00');
  });

  test('blurring a changed PID runs lookup without showing No AD match', async ({ page }) => {
    const lookupRequests = [];
    await stubReviewApis(
      page,
      buildExtractionFailedPreview({
        pids: [{ pid: '987654321', active_directory: { status: 'found', name: AD_NAME } }],
      }),
      {
        onLookup: (pids) => {
          lookupRequests.push(...pids);
        },
      }
    );
    await uploadAndOpenReview(page);

    const pidInput = page.getByLabel('PID for check 1');
    await pidInput.fill(FIXED_PID);
    await page.getByLabel('Amount for check 1').click();

    await expect.poll(() => lookupRequests).toContain(FIXED_PID);
    await expect(page.getByText(/No AD match/i)).toHaveCount(0);
    await expect(page.getByText(AD_NAME, { exact: true })).toBeVisible({ timeout: 10_000 });
  });

  test('supporting flag plus incomplete PID amount split does not emphasize Mark verified', async ({ page }) => {
    const image = preview.checks[0].front_image;
    const mixedIssuePreview = {
      ...preview,
      checks: [
        {
          ...preview.checks[0],
          provider: 'Example Foundation',
          amount: '250.00',
          name: 'Alex Example',
          supporting_pages: [2],
          supporting_images: [image],
          supporting_looks_like_check: true,
          extraction_failed: false,
          pids: [
            { pid: FIXED_PID, amount: '100.00', active_directory: { status: 'found', name: AD_NAME } },
            { pid: '987654321', amount: null, active_directory: { status: 'found', name: AD_NAME } },
          ],
        },
      ],
    };
    await stubReviewApis(page, mixedIssuePreview);
    await uploadAndOpenReview(page);

    const needsReviewBox = page.getByRole('status').filter({ hasText: 'Needs review' });
    await expect(needsReviewBox).toContainText('Supporting looks like check');
    await expect(needsReviewBox).toContainText('Amount not split');
    await expect(needsReviewBox).toContainText(SUPPORTING_RESOLUTION);

    const verifyButton = page.getByRole('button', { name: 'Mark verified' });
    await expect(verifyButton).toBeEnabled();
    await expect(verifyButton).not.toHaveAttribute('data-emphasis', 'resolve-flag');

    const artifactsDir = path.join(__dirname, 'artifacts');
    fs.mkdirSync(artifactsDir, { recursive: true });
    await page.screenshot({
      path: path.join(artifactsDir, 'outside-scholarships-supporting-plus-incomplete-split.png'),
      fullPage: true,
    });
  });

  test('supporting flag plus malformed PID explains why Mark verified is disabled', async ({ page }) => {
    const image = preview.checks[0].front_image;
    const malformedPidPreview = {
      ...preview,
      checks: [
        {
          ...preview.checks[0],
          provider: 'Example Foundation',
          amount: '250.00',
          name: 'Alex Example',
          supporting_pages: [2],
          supporting_images: [image],
          supporting_looks_like_check: true,
          extraction_failed: false,
          pids: [{ pid: '12345678', active_directory: { status: 'not_found', name: null } }],
        },
      ],
    };
    await stubReviewApis(page, malformedPidPreview);
    await uploadAndOpenReview(page);

    const needsReviewBox = page.getByRole('status').filter({ hasText: 'Needs review' });
    await expect(needsReviewBox).toContainText('Supporting looks like check');
    await expect(needsReviewBox).toContainText('Bad PID');
    await expect(needsReviewBox).toContainText(SUPPORTING_RESOLUTION);
    await expect(needsReviewBox).toContainText(BAD_PID_VERIFY_GUIDANCE);

    const verifyButton = page.getByRole('button', { name: 'Mark verified' });
    await expect(verifyButton).toBeDisabled();
    await expect(verifyButton).not.toHaveAttribute('data-emphasis', 'resolve-flag');
    await expect(verifyButton).toHaveAccessibleDescription(BAD_PID_VERIFY_GUIDANCE);
  });

  test('supporting and extraction flags together emphasize Mark verified with both resolutions', async ({ page }) => {
    const image = preview.checks[0].front_image;
    const verifyResolvablePreview = {
      ...preview,
      checks: [
        {
          ...preview.checks[0],
          provider: 'Example Foundation',
          amount: '250.00',
          name: 'Alex Example',
          supporting_pages: [2],
          supporting_images: [image],
          supporting_looks_like_check: true,
          extraction_failed: true,
          pids: [{ pid: FIXED_PID, active_directory: { status: 'found', name: AD_NAME } }],
        },
      ],
    };
    await stubReviewApis(page, verifyResolvablePreview);
    await uploadAndOpenReview(page);

    const needsReviewBox = page.getByRole('status').filter({ hasText: 'Needs review' });
    await expect(needsReviewBox).toContainText('Supporting looks like check');
    await expect(needsReviewBox).toContainText('Extraction failed');
    await expect(needsReviewBox).toContainText(SUPPORTING_RESOLUTION);
    await expect(needsReviewBox).toContainText(EXTRACTION_RESOLUTION);

    const verifyButton = page.getByRole('button', { name: 'Mark verified' });
    await expect(verifyButton).toHaveAttribute('data-emphasis', 'resolve-flag');
    await expect(verifyButton).toHaveAccessibleDescription(
      /Open the Supporting page[\s\S]*Check each field against the images/i
    );
  });

  test('Mark verified emphasis follows the selected check', async ({ page }) => {
    const image = preview.checks[0].front_image;
    const multiCheckPreview = {
      ...preview,
      checks: [
        {
          ...preview.checks[0],
          check_index: 1,
          provider: 'Example Foundation',
          amount: '250.00',
          name: 'Alex Example',
          supporting_pages: [2],
          supporting_images: [image],
          supporting_looks_like_check: true,
          extraction_failed: false,
          pids: [{ pid: FIXED_PID, active_directory: { status: 'found', name: AD_NAME } }],
        },
        {
          ...preview.checks[0],
          check_index: 2,
          check_number: '1002',
          provider: 'Example Foundation',
          amount: '250.00',
          name: 'Alex Example',
          supporting_pages: [3],
          supporting_images: [image],
          supporting_looks_like_check: true,
          extraction_failed: false,
          pids: [
            { pid: FIXED_PID, amount: '100.00', active_directory: { status: 'found', name: AD_NAME } },
            { pid: '987654321', amount: null, active_directory: { status: 'found', name: AD_NAME } },
          ],
        },
      ],
    };
    await stubReviewApis(page, multiCheckPreview);
    await uploadAndOpenReview(page);

    const verifyButton = page.getByRole('button', { name: 'Mark verified' });
    await expect(page.getByRole('option', { name: /Check 1/i })).toHaveAttribute(
      'aria-selected',
      'true'
    );
    await expect(verifyButton).toHaveAttribute('data-emphasis', 'resolve-flag');
    await expect(verifyButton).toHaveAccessibleDescription(SUPPORTING_RESOLUTION);

    await page.getByRole('option', { name: /Check 2/i }).click();
    await expect(page.getByRole('option', { name: /Check 2/i })).toHaveAttribute(
      'aria-selected',
      'true'
    );
    const needsReviewBox = page.getByRole('status').filter({ hasText: 'Needs review' });
    await expect(needsReviewBox).toContainText('Amount not split');
    await expect(verifyButton).not.toHaveAttribute('data-emphasis', 'resolve-flag');
  });

  test('complete multi-PID amount split exports per-PID amounts after verification', async ({ page }) => {
    let exportBody = null;
    const splitPreview = {
      ...preview,
      checks: [
        {
          ...preview.checks[0],
          provider: 'Example Foundation',
          supporting_looks_like_check: false,
          pids: [
            { pid: FIXED_PID, amount: '100.00', active_directory: { status: 'found', name: AD_NAME } },
            { pid: '987654321', amount: '150.00', active_directory: { status: 'found', name: AD_NAME } },
          ],
        },
      ],
    };
    await stubReviewApis(page, splitPreview, { onExport: (body) => { exportBody = body; } });
    await uploadAndOpenReview(page);

    await expect(page.getByText(/Split matches check total/i)).toBeVisible();
    await expect(page.getByText(/Amount not split/i)).toBeHidden();
    await expect(page.getByText(/Supporting looks like check/i)).toBeHidden();
    await expect(page.getByText(/Multiple PIDs/i).first()).toBeVisible();

    await page.getByRole('button', { name: 'Mark verified' }).click();
    const downloadPromise = page.waitForEvent('download');
    await page.getByRole('button', { name: 'Export Excel' }).click();
    await downloadPromise;

    expect(exportBody.checks[0].reviewed.pids.map((entry) => entry.amount)).toEqual([
      '100.00',
      '150.00',
    ]);
  });

  test('incomplete multi-PID amount split can be manually verified without clearing PID amounts', async ({ page }) => {
    let exportBody = null;
    const incompletePreview = {
      ...preview,
      checks: [
        {
          ...preview.checks[0],
          provider: 'Example Foundation',
          pids: [
            { pid: FIXED_PID, amount: '100.00', active_directory: { status: 'found', name: AD_NAME } },
            { pid: '987654321', amount: null, active_directory: { status: 'found', name: AD_NAME } },
          ],
        },
      ],
    };
    await stubReviewApis(page, incompletePreview, { onExport: (body) => { exportBody = body; } });
    await uploadAndOpenReview(page);

    await expect(page.getByText(/Amount not split/i).first()).toBeVisible();
    // Split issues are fixed by editing amounts, so Mark verified is not emphasized here.
    await expect(page.getByRole('button', { name: 'Mark verified' })).not.toHaveAttribute(
      'data-emphasis',
      'resolve-flag'
    );
    await expect(
      page.getByText(/Amounts not split\. Excel will use \$250\.00 on every PID row until the split matches\./i)
    ).toBeVisible();
    await expect(page.getByRole('button', { name: 'Export Excel' })).toBeDisabled();

    await page.getByRole('button', { name: 'Mark verified' }).click();
    await expect(page.getByRole('button', { name: 'Undo' })).toBeVisible();
    await expect(
      page.getByText(/Amounts not split\. Excel will use \$250\.00 on every PID row until the split matches\./i)
    ).toBeVisible();
    await expect(page.getByRole('button', { name: 'Export Excel' })).toBeEnabled();

    const downloadPromise = page.waitForEvent('download');
    await page.getByRole('button', { name: 'Export Excel' }).click();
    await downloadPromise;

    expect(exportBody.checks[0].reviewed.pids.map((entry) => entry.amount)).toEqual([
      '100.00',
      null,
    ]);
  });

  test('AD/payee name mismatch blocks export until corrected', async ({ page }) => {
    const mismatchName = 'Mismatch, Morgan';
    const mismatchPreview = {
      ...preview,
      checks: [
        {
          ...preview.checks[0],
          provider: 'Example Foundation',
          pids: [{ pid: FIXED_PID, active_directory: { status: 'found', name: mismatchName } }],
        },
      ],
    };
    await stubReviewApis(page, mismatchPreview, {
      lookupByPid: (pid) =>
        pid === FIXED_PID
          ? { status: 'found', name: mismatchName }
          : { status: 'not_found', name: null },
    });
    await uploadAndOpenReview(page);

    await expect(page.getByText(/Name mismatch/i).first()).toBeVisible();
    const payeeInput = page.getByLabel('Payee name for check 1');
    await expect(payeeInput).toHaveAttribute('aria-invalid', 'true');
    await expect(page.getByRole('button', { name: 'Export Excel' })).toBeDisabled();

    await payeeInput.fill('Morgan Mismatch');

    await expect(page.getByText(/Name mismatch/i).first()).toBeHidden();
    await expect(payeeInput).not.toHaveAttribute('aria-invalid', 'true');
    await expect(page.getByRole('button', { name: 'Export Excel' })).toBeEnabled();

    const artifactsDir = path.join(__dirname, 'artifacts');
    fs.mkdirSync(artifactsDir, { recursive: true });
    await page.screenshot({ path: path.join(artifactsDir, 'outside-scholarships-name-mismatch-resolved.png'), fullPage: true });
  });

  // Typing a valid short provider must not auto-advance mid-edit.
  test('provider draft does not auto-advance while editing', async ({ page }) => {
    const longProvider = 'Henderson County Education Foundation Inc';
    expect(longProvider.length).toBeGreaterThan(30);

    const okPid = {
      pid: FIXED_PID,
      active_directory: { status: 'found', name: AD_NAME },
    };
    const multiCheckPreview = {
      ...preview,
      checks: [
        {
          ...preview.checks[0],
          check_index: 1,
          provider: longProvider,
          pids: [okPid],
        },
        {
          ...preview.checks[0],
          check_index: 2,
          check_number: '1002',
          provider: '',
          pids: [okPid],
        },
      ],
    };
    await stubReviewApis(page, multiCheckPreview);
    await uploadAndOpenReview(page);

    await expect(page.getByText(/Provider too long/i).first()).toBeVisible();
    await expect(page.getByRole('option', { name: /Check 1/i })).toHaveAttribute(
      'aria-selected',
      'true'
    );

    const providerInput = page.getByLabel('Provider for check 1');
    await expect(providerInput).toHaveValue(longProvider);
    await providerInput.click();
    await providerInput.fill('Short Provider');
    await expect(providerInput).toHaveValue('Short Provider');

    // Still on check 1 — uncommitted draft must not clear Needs review / auto-advance.
    await expect(page.getByRole('option', { name: /Check 1/i })).toHaveAttribute(
      'aria-selected',
      'true'
    );
    await expect(page.getByText(/Provider too long/i).first()).toBeVisible();

    await providerInput.press('Escape');
    await expect(providerInput).toHaveValue(longProvider);

    await providerInput.fill('Short Provider');
    await providerInput.press('Enter');

    await expect(page.getByRole('option', { name: /Check 2/i })).toHaveAttribute(
      'aria-selected',
      'true',
      { timeout: 10_000 }
    );
    await expect(page.getByText(/Missing provider/i).first()).toBeVisible();
  });

  // Typing a valid amount must not auto-advance mid-edit.
  test('amount draft does not auto-advance while editing', async ({ page }) => {
    const okPid = {
      pid: FIXED_PID,
      active_directory: { status: 'found', name: AD_NAME },
    };
    const multiCheckPreview = {
      ...preview,
      checks: [
        {
          ...preview.checks[0],
          check_index: 1,
          amount: '',
          provider: 'Example Foundation',
          pids: [okPid],
        },
        {
          ...preview.checks[0],
          check_index: 2,
          check_number: '1002',
          amount: '10.00',
          provider: '',
          pids: [okPid],
        },
      ],
    };
    await stubReviewApis(page, multiCheckPreview);
    await uploadAndOpenReview(page);

    await expect(page.getByText(/Missing amount/i).first()).toBeVisible();
    await expect(page.getByRole('option', { name: /Check 1/i })).toHaveAttribute(
      'aria-selected',
      'true'
    );

    const amountInput = page.getByLabel('Amount for check 1');
    await amountInput.click();
    await amountInput.fill('250.00');
    await expect(amountInput).toHaveValue('250.00');

    await expect(page.getByRole('option', { name: /Check 1/i })).toHaveAttribute(
      'aria-selected',
      'true'
    );
    await expect(page.getByText(/Missing amount/i).first()).toBeVisible();

    await amountInput.press('Escape');
    await expect(amountInput).toHaveValue('');

    await amountInput.fill('250.00');
    await amountInput.press('Enter');

    await expect(page.getByRole('option', { name: /Check 2/i })).toHaveAttribute(
      'aria-selected',
      'true',
      { timeout: 10_000 }
    );
    await expect(page.getByText(/Missing provider/i).first()).toBeVisible();
  });

  test('supporting thumbnails open, and a document term survives the header term', async ({ page }) => {
    const image = preview.checks[0].front_image;
    const okPid = {
      pid: FIXED_PID,
      active_directory: { status: 'found', name: AD_NAME },
    };
    const supportingPreview = {
      ...preview,
      aid_term: 'F',
      checks: [
        {
          ...preview.checks[0],
          check_index: 1,
          provider: 'Example Foundation',
          amount: '250.00',
          name: 'Alex Example',
          scholarship_name: 'Wells Fargo Award',
          aid_term: 'F/S',
          supporting_pages: [2],
          supporting_images: [image],
          pids: [okPid],
        },
        {
          ...preview.checks[0],
          check_index: 2,
          check_number: '1002',
          provider: 'Other Foundation',
          amount: '10.00',
          name: 'Alex Example',
          scholarship_name: 'Other Award',
          aid_term: null,
          supporting_pages: [],
          supporting_images: [],
          pids: [okPid],
        },
      ],
    };

    let exportBody = null;
    await stubReviewApis(page, supportingPreview);
    await page.route('**/api/banking/outside-scholarships/export', async (route) => {
      exportBody = route.request().postDataJSON();
      await route.fulfill({
        status: 200,
        contentType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers: {
          'content-disposition': 'attachment; filename="outside_scholarships_reviewed.xlsx"',
        },
        body: Buffer.from('PK-fake-xlsx'),
      });
    });

    await page.goto('/e2e/outside-scholarships');
    await expect(page.getByText(/then that check's letters or forms, then the next check/i)).toBeVisible();

    const pdfBytes = Buffer.from('%PDF-1.1\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n', 'utf8');
    await page.setInputFiles('input[type="file"]', {
      name: 'sample-checks.pdf',
      mimeType: 'application/pdf',
      buffer: pdfBytes,
    });
    await page.getByRole('button', { name: 'Upload Check PDF' }).click();

    await expect(page.getByRole('button', { name: /Enlarge Supporting page 1 of check 1/i })).toBeVisible();
    await page.getByRole('button', { name: /Enlarge Supporting page 1 of check 1/i }).click();
    await expect(page.getByRole('dialog', { name: 'Supporting page 1 of check 1' })).toBeVisible();
    await page.getByRole('button', { name: 'Close' }).click();

    const checkTerm = page.getByRole('combobox', { name: 'Aid term for check 1' });
    await expect(checkTerm).toHaveValue('F/S');
    await expect(page.getByText("Read from this check's pages.")).toBeVisible();

    await page.getByRole('combobox', { name: 'Aid term', exact: true }).selectOption('S');
    await expect(checkTerm).toHaveValue('F/S');

    await page.getByRole('option', { name: /Check 2/i }).click();
    await expect(page.getByRole('combobox', { name: 'Aid term for check 2' })).toHaveValue('S');
    await expect(page.getByText('No supporting pages for this check.')).toBeVisible();

    await page.getByRole('button', { name: 'Export Excel' }).click();
    await expect.poll(() => exportBody).not.toBeNull();
    expect(exportBody.aid_term).toBe('S');
    expect(exportBody.checks[0].extracted.aid_term).toBe('F/S');
    expect(exportBody.checks[0].reviewed.aid_term).toBe('F/S');
    // Check 2 had no document term — extracted stays blank; reviewed uses the header fallback.
    expect(exportBody.checks[1].extracted.aid_term).toBeNull();
    expect(exportBody.checks[1].reviewed.aid_term).toBe('S');
  });
});
