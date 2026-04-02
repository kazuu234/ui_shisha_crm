import { test, expect } from '@playwright/test';
import type { Page } from '@playwright/test';

import { STAFF_TOKEN_FLOW2, CUSTOMER_NAME } from '../fixtures/test-data';

test.describe.serial('Flow 2: staff session', () => {
  let page: Page | undefined;
  /** `test_visit_create_with_toast` 実行直前の `#recent-visits` 内の来店行数（border-b 行） */
  let recentVisitRowCountBeforeCreate = 0;

  test.beforeAll(async ({ browser }) => {
    page = await browser.newPage();
    await page.goto(`/s/login/#token=${STAFF_TOKEN_FLOW2}`);
    await page.waitForURL('**/s/customers/**');
  });

  test.afterAll(async () => {
    await page?.close();
  });

  test('test_customer_search_htmx', async () => {
    if (!page) throw new Error('page not initialized');
    await page.getByRole('button', { name: '顧客を検索' }).click();
    await expect(page.locator('input[name="q"]')).toBeVisible();
    await page.locator('input[name="q"]').fill('E2E');
    await expect(page.getByText(CUSTOMER_NAME, { exact: false })).toBeVisible({ timeout: 3000 });
  });

  test('test_navigate_to_session', async () => {
    if (!page) throw new Error('page not initialized');
    await page.locator('#search-results a[href*="/session/"]').first().click();
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
    recentVisitRowCountBeforeCreate = await recent.locator('> div.border-b').count();
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
    const afterCount = await recent.locator('> div.border-b').count();
    expect(afterCount).toBeGreaterThan(recentVisitRowCountBeforeCreate);

    const today = new Date();
    const todayStr = `${today.getMonth() + 1}/${today.getDate()}`;
    await expect(recent.getByText(todayStr)).toBeVisible({ timeout: 3000 });
    await expect(recent.getByText('E2E Staff')).toBeVisible({ timeout: 3000 });
  });
});
