const { test, expect } = require('@playwright/test');
const fs = require('fs');
const path = require('path');

const preview = JSON.parse(
  fs.readFileSync(path.join(__dirname, 'fixtures', 'preview.json'), 'utf8')
);

const FIXED_PID = '123456789';
const AD_NAME = 'Example, Alex';

async function stubReviewApis(page, previewBody) {
  await page.route('**/api/banking/outside-scholarships/active-directory-names', async (route) => {
    const body = route.request().postDataJSON();
    const pids = Array.isArray(body?.pids) ? body.pids : [];
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        pids: pids.map((pid) => ({
          pid,
          active_directory:
            pid === FIXED_PID
              ? { status: 'found', name: AD_NAME }
              : { status: 'not_found', name: null },
        })),
      }),
    });
  });

  await page.route('**/api/banking/outside-scholarships/export', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      headers: {
        'content-disposition': 'attachment; filename="outside_scholarships_reviewed.xlsx"',
      },
      body: Buffer.from('PK-fake-xlsx'),
    });
  });

  await page.route('**/api/banking/outside-scholarships', async (route) => {
    if (route.request().method() !== 'POST') {
      await route.continue();
      return;
    }
    // Exclude nested routes handled above
    const url = route.request().url();
    if (url.includes('active-directory-names') || url.includes('/export')) {
      await route.continue();
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(previewBody),
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

  test('long provider is truncated and does not block export', async ({ page }) => {
    const longProvider = 'North Carolina Community Foundation Scholarship Fund';
    expect(longProvider.length).toBeGreaterThan(30);
    const truncatedProvider = longProvider.slice(0, 30);

    const longProviderPreview = {
      ...preview,
      checks: [
        {
          ...preview.checks[0],
          provider: longProvider,
          pids: [{ pid: FIXED_PID, active_directory: { status: 'found', name: AD_NAME } }],
        },
      ],
    };
    await stubReviewApis(page, longProviderPreview);
    await uploadAndOpenReview(page);

    await expect(page.getByText(/Provider too long/i)).toHaveCount(0);
    const providerInput = page.getByLabel('Provider for check 1');
    await expect(providerInput).toHaveValue(truncatedProvider);
    await expect(providerInput).toHaveJSProperty('value', truncatedProvider);
    expect((await providerInput.inputValue()).length).toBeLessThanOrEqual(30);

    await expect(page.getByText(/0 of 1 left/i).first()).toBeVisible();
    await expect(page.getByRole('button', { name: 'Export Excel' })).toBeEnabled();
  });
});
