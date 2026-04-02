import { test, expect } from '@playwright/test';
import type { BrowserContext, Page } from '@playwright/test';

import { STAFF_TOKEN } from '../fixtures/test-data';

const BASE_URL = 'http://localhost:8000';
const TZ = 'Asia/Tokyo';

test.describe.serial('Flow 1: staff QR login', () => {
  let page: Page | undefined;
  let context: BrowserContext | undefined;

  test.beforeAll(async ({ browser }) => {
    context = await browser.newContext({ baseURL: BASE_URL, timezoneId: TZ });
    page = await context.newPage();
    await page.goto(`/s/login/#token=${STAFF_TOKEN}`);
    await page.waitForURL('**/s/customers/**');
  });

  test.afterAll(async () => {
    await context?.close();
  });

  test('test_qr_link_auto_login', async () => {
    if (!page) throw new Error('page not initialized');
    await expect(page).toHaveURL(/\/s\/customers\/?(\?.*)?$/);
    expect(page.url()).not.toContain('#token=');
    await expect(page.getByRole('button', { name: '顧客を検索' })).toBeVisible();
  });

  test('test_hash_removed_after_login', async () => {
    if (!page) throw new Error('page not initialized');
    const hash = await page.evaluate(() => window.location.hash);
    expect(hash).toBe('');
  });

  test('test_back_button_no_resubmit', async () => {
    if (!page) throw new Error('page not initialized');
    await page.goBack();
    await expect(page.getByText('この QR コードは既に使用されています')).toHaveCount(0);
    const url = page.url();
    expect(url.includes('/s/login/') || url.includes('/s/customers/')).toBeTruthy();
  });

  test('test_session_persists', async () => {
    if (!page) throw new Error('page not initialized');
    await page.goto('/s/customers/');
    await expect(page).toHaveURL(/\/s\/customers\/?(\?.*)?$/);
    await expect(page.getByRole('button', { name: '顧客を検索' })).toBeVisible();
  });
});

test('test_unauthenticated_redirect', async ({ browser }) => {
  const context = await browser.newContext({ baseURL: BASE_URL, timezoneId: TZ });
  const fresh = await context.newPage();
  await fresh.goto('/s/customers/');
  await fresh.waitForURL('**/s/login/**');
  await expect(fresh).toHaveURL(/\/s\/login\//);
  await context.close();
});
