import { Page } from '@playwright/test';
import { STAFF_TOKEN, OWNER_TOKEN } from '../fixtures/test-data';

export async function staffLogin(page: Page): Promise<void> {
  await page.goto(`/s/login/#token=${STAFF_TOKEN}`);
  await page.waitForURL('/s/customers/');
}

export async function ownerLogin(page: Page): Promise<void> {
  await page.goto(`/o/login/#token=${OWNER_TOKEN}`);
  await page.waitForURL('/o/dashboard/');
}
