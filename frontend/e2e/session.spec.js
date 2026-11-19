const { test, expect } = require('@playwright/test');

const MINUTE_MS = 60 * 1000;

test.describe('session lifetime', () => {
  test('stays signed in when a session passes the old 30-minute mark', async ({ page }) => {
    await page.clock.install();
    await page.addInitScript((signedInAgoMs) => {
      window.__e2eLogoutCalls = 0;
      window.localStorage.setItem('session_login_timestamp', String(Date.now() - signedInAgoMs));
    }, 29 * MINUTE_MS);

    await page.goto('/e2e/session');
    await expect(page.getByRole('button', { name: /Account menu for E2E User/i })).toBeVisible();

    await page.clock.fastForward(2 * MINUTE_MS);

    await expect(page.getByRole('button', { name: /Account menu for E2E User/i })).toBeVisible();
    await expect(page.getByTitle('Session time remaining')).toHaveCount(0);
    expect(await page.evaluate(() => window.__e2eLogoutCalls)).toBe(0);
  });
});
