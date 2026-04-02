import { test, expect } from '@playwright/test';
import type { Page } from '@playwright/test';

import { OWNER_TOKEN } from '../fixtures/test-data';

async function expectThreeChartsRendered(page: Page): Promise<void> {
  const canvases = page.locator('canvas');
  await expect(canvases).toHaveCount(3);
  for (let i = 0; i < 3; i++) {
    const canvas = canvases.nth(i);
    await expect(async () => {
      const box = await canvas.boundingBox();
      expect(box).not.toBeNull();
      expect(box!.width).toBeGreaterThan(0);
      expect(box!.height).toBeGreaterThan(0);
    }).toPass({ timeout: 5000 });

    const hasChart = await canvas.evaluate((el: HTMLCanvasElement) => {
      // Chart.js は getChart() で canvas に紐づく Chart インスタンスを返す
      // @ts-expect-error Chart はページのグローバルに読み込まれている
      return typeof Chart !== 'undefined' && Chart.getChart(el) != null;
    });
    expect(hasChart).toBeTruthy();
  }
}

test.describe.serial('Flow 3: owner dashboard', () => {
  let page: Page | undefined;

  test.beforeAll(async ({ browser }) => {
    page = await browser.newPage();
    await page.goto(`/o/login/#token=${OWNER_TOKEN}`);
    await page.waitForURL('**/o/dashboard/**');
  });

  test.afterAll(async () => {
    await page?.close();
  });

  test('test_owner_qr_login', async () => {
    if (!page) throw new Error('page not initialized');
    await expect(page).toHaveURL(/\/o\/dashboard\/?(\?.*)?$/);
    expect(page.url()).not.toContain('#token=');
  });

  test('test_dashboard_charts_rendered', async () => {
    if (!page) throw new Error('page not initialized');
    await expect(page.locator('#chart-daily')).toBeAttached();
    await expect(page.locator('#chart-segment')).toBeAttached();
    await expect(page.locator('#chart-staff')).toBeAttached();
    await expectThreeChartsRendered(page);
  });

  test('test_dashboard_kpi_cards', async () => {
    if (!page) throw new Error('page not initialized');
    await expect(page.getByText('今日の来客数')).toBeVisible();
    await expect(page.getByText('今月の来客数')).toBeVisible();
    await expect(page.getByText('新規率')).toBeVisible();
    await expect(page.getByText('アクティブ顧客数')).toBeVisible();
    const values = page.locator('p.text-2xl.font-bold.text-text-primary');
    await expect(values).toHaveCount(4);
    for (let i = 0; i < 4; i++) {
      await expect(values.nth(i)).not.toHaveText('');
    }
  });

  test('test_period_filter_htmx', async () => {
    if (!page) throw new Error('page not initialized');
    const select = page.locator('select[name="period"]');
    const current = await select.inputValue();
    const next = current === '7' ? '30' : '7';

    const oldDailyData = await page.locator('#daily-data').elementHandle();

    const [response] = await Promise.all([
      page.waitForResponse((r) => {
        if (!r.url().includes('/o/dashboard/') || r.request().method() !== 'GET') return false;
        return r.request().headers()['hx-request'] === 'true';
      }),
      select.selectOption(next),
    ]);

    expect(response.ok()).toBeTruthy();
    await expect(page).toHaveURL(new RegExp(`period=${next}`));

    if (oldDailyData) {
      const isDetached = await oldDailyData.evaluate((el) => !el.isConnected);
      expect(isDetached).toBeTruthy();
    }

    await expect(page.locator('#daily-data')).toBeAttached();

    await expectThreeChartsRendered(page);
  });

  test('test_sidebar_navigation', async () => {
    if (!page) throw new Error('page not initialized');
    await page.locator('aside a[href="/o/customers/"]').click();
    await page.waitForURL('**/o/customers/**');
    await expect(page).toHaveURL(/\/o\/customers\/?(\?.*)?$/);
  });
});
