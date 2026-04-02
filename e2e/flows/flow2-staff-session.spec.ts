import { test, expect } from '@playwright/test';
import type { BrowserContext, Page } from '@playwright/test';

import { STAFF_TOKEN_FLOW2, CUSTOMER_NAME, CUSTOMER_ID } from '../fixtures/test-data';

const BASE_URL = 'http://localhost:8000';
const TZ = 'Asia/Tokyo';

test.describe.serial('Flow 2: staff session', () => {
  let page: Page | undefined;
  let context: BrowserContext | undefined;
  let recentVisitsHtmlBeforeCreate = '';
  let recentVisitsCountBefore = 0;

  test.beforeAll(async ({ browser }) => {
    context = await browser.newContext({ baseURL: BASE_URL, timezoneId: TZ });
    page = await context.newPage();
    await page.goto(`/s/login/#token=${STAFF_TOKEN_FLOW2}`);
    await page.waitForURL('**/s/customers/**');
  });

  test.afterAll(async () => {
    await context?.close();
  });

  test('test_customer_search_htmx', async () => {
    if (!page) throw new Error('page not initialized');
    await page.getByRole('button', { name: '顧客を検索' }).click();
    await expect(page.locator('input[name="q"]')).toBeVisible();
    await page.locator('input[name="q"]').fill('E2E');
    // #search-results 内に顧客名が表示されることを確認（HTMX 部分更新の検証）
    await expect(
      page.locator('#search-results').getByText(CUSTOMER_NAME, { exact: false }),
    ).toBeVisible({ timeout: 3000 });
  });

  test('test_navigate_to_session', async () => {
    if (!page) throw new Error('page not initialized');
    await page.locator(`#search-results a[href*="${CUSTOMER_ID}"]`).click();
    await page.waitForURL('**/session/**');
    await expect(page.getByRole('heading', { name: 'ヒアリングタスク' })).toBeVisible();
  });

  test('test_task_zone_visible', async () => {
    if (!page) throw new Error('page not initialized');
    await expect(page.locator('#zone-age')).toBeVisible();
    await expect(page.locator('#zone-area')).toBeVisible();
    await expect(page.locator('#zone-shisha_experience')).toBeVisible();
  });

  test('test_task_zone_expand', async () => {
    if (!page) throw new Error('page not initialized');
    const zone = page.locator('#zone-shisha_experience');
    await zone.getByRole('button', { name: /タップして/ }).click();
    await expect(zone.getByRole('button', { name: '初心者' })).toBeVisible({ timeout: 3000 });
  });

  test('test_task_field_update', async () => {
    if (!page) throw new Error('page not initialized');
    const zone = page.locator('#zone-age');
    await zone.getByRole('button', { name: /タップして/ }).click();
    await zone.getByRole('button', { name: '20代' }).click();
    await expect(zone.locator('.bg-accent-light').filter({ hasText: '20代' })).toBeVisible({
      timeout: 3000,
    });
    await expect(zone.getByRole('button', { name: /タップして/ })).toHaveCount(0);
    // age は消化済み、area / shisha_experience は未消化（未消化タスクが 2 件）
    await expect(page.locator('#zone-age .bg-accent-light')).toBeVisible();
    await expect(page.locator('#zone-area .bg-accent-light')).toHaveCount(0);
    await expect(page.locator('#zone-shisha_experience .bg-accent-light')).toHaveCount(0);
  });

  test('test_visit_create_with_toast', async () => {
    if (!page) throw new Error('page not initialized');
    const recent = page.locator('#recent-visits');
    recentVisitsHtmlBeforeCreate = await recent.innerHTML();
    recentVisitsCountBefore = await recent.locator(':scope > div.border-b').count();
    await Promise.all([
      page.waitForResponse(
        (r) =>
          r.url().includes('/session/recent-visits/') &&
          r.request().method() === 'GET' &&
          r.request().headers()['hx-request'] === 'true',
      ),
      page.getByRole('button', { name: '来店記録を作成する' }).click(),
    ]);
    const toast = page.getByText('来店記録を作成しました');
    await expect(toast).toBeVisible({ timeout: 3000 });
    await expect(toast).toBeHidden({ timeout: 6000 });
  });

  test('test_recent_visits_updated', async () => {
    if (!page) throw new Error('page not initialized');
    const recent = page.locator('#recent-visits');
    const afterCount = await recent.locator(':scope > div.border-b').count();
    const afterHtml = await recent.innerHTML();
    expect(
      afterCount > recentVisitsCountBefore || afterHtml !== recentVisitsHtmlBeforeCreate,
    ).toBe(true);

    const firstRow = recent.locator(':scope > div.border-b').first();
    await expect(firstRow).toBeVisible({ timeout: 3000 });
    await expect(firstRow.getByText('E2E Staff')).toBeVisible({ timeout: 3000 });
  });
});
