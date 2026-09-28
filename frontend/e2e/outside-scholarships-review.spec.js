const { test, expect } = require('@playwright/test');
const fs = require('fs');
const path = require('path');

const preview = JSON.parse(
  fs.readFileSync(path.join(__dirname, 'fixtures', 'preview.json'), 'utf8')
);

const FIXED_PID = '123456789';
const AD_NAME = 'Example, Alex';

test.describe('Outside scholarships review flow', () => {
  test('upload → fix PID → AD name → export', async ({ page }) => {
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
        body: JSON.stringify(preview),
      });
    });

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
    await expect(page.getByText('1 checks need review').first()).toBeVisible();
    await expect(page.getByRole('button', { name: 'Export Excel' })).toBeDisabled();

    const pidInput = page.getByLabel('PID for check 1');
    await expect(pidInput).toHaveValue('12345');
    await pidInput.fill(FIXED_PID);
    await pidInput.press('Enter');

    await expect(page.getByText(AD_NAME, { exact: true })).toBeVisible({ timeout: 10_000 });
    await expect(page.getByText(/Missing: provider/i)).toBeVisible();

    // Resolve remaining flag via Mark verified (workflow aid — export does not re-validate).
    const verifyButton = page.getByRole('button', { name: 'Mark verified' });
    await verifyButton.scrollIntoViewIfNeeded();
    await verifyButton.click();
    await expect(page.getByRole('button', { name: 'Undo' })).toBeVisible({ timeout: 10_000 });
    await expect(page.getByText('0 checks need review').first()).toBeVisible();

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
});
