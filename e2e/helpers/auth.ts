import { Page } from '@playwright/test';
import { STAFF_TOKEN, STAFF_TOKEN_FLOW2, OWNER_TOKEN } from '../fixtures/test-data';

export async function staffLogin(page: Page): Promise<void> {
  await page.goto(`/s/login/#token=${STAFF_TOKEN}`);
  await page.waitForURL('/s/customers/');
}

export async function staffLoginFlow2(page: Page): Promise<void> {
  await page.goto(`/s/login/#token=${STAFF_TOKEN_FLOW2}`);
  await page.waitForURL('**/s/customers/**');
}

export async function ownerLogin(page: Page): Promise<void> {
  await page.goto(`/o/login/#token=${OWNER_TOKEN}`);
  await page.waitForURL('/o/dashboard/');
}
