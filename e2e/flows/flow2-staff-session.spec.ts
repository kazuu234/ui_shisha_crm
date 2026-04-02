import { test, expect } from '@playwright/test';
import type { Page } from '@playwright/test';

import { STAFF_TOKEN, CUSTOMER_NAME } from '../fixtures/test-data';

/** Flow 1 で STAFF_TOKEN を消費するため、フルスイート時は 2 つ目のトークンを渡す */
const flow2StaffToken = process.env.E2E_STAFF_TOKEN_FLOW2 ?? STAFF_TOKEN;

test.describe.serial('Flow 2: staff session', () => {
  let page: Page | undefined;

  test.beforeAll(async ({ browser }) => {
    page = await browser.newPage();
    await page.goto(`/s/login/#token=${flow2StaffToken}`);
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
  });

  test('test_visit_create_with_toast', async () => {
    if (!page) throw new Error('page not initialized');
    await page.getByRole('button', { name: '来店記録を作成する' }).click();
    const toast = page.getByText('来店記録を作成しました');
    await expect(toast).toBeVisible({ timeout: 3000 });
    await expect(toast).toBeHidden({ timeout: 6000 });
  });

  test('test_recent_visits_updated', async () => {
    if (!page) throw new Error('page not initialized');
    const recent = page.locator('#recent-visits');
    await expect(recent.getByText(/\d+\/\d+/)).toBeVisible({ timeout: 3000 });
    await expect(recent.getByText('E2E Staff')).toBeVisible({ timeout: 3000 });
  });
});
