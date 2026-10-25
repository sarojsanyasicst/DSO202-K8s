import type { Browser, Page } from '@playwright/test';

import { addToCart, expect, product, test } from './support/fixtures';
import { ADMIN_PASSWORD } from './support/stack';

const ORDER_URL = /\/orders\/[0-9a-f-]{36}$/;

async function signIn(page: Page, password = ADMIN_PASSWORD): Promise<void> {
  await page.goto('/admin');
  await page.getByLabel('Username').fill('instructor');
  await page.getByLabel('Password').fill(password);
  await page.getByRole('button', { name: 'Sign in' }).click();
}

/** A separate guest who buys one unit of `name` and returns the new order's id. */
async function guestBuys(browser: Browser, name: string): Promise<string> {
  const context = await browser.newContext();
  const page = await context.newPage();
  await page.goto('/');
  await addToCart(page, name);
  await page.getByRole('link', { name: /^Cart, / }).click();
  await page.getByRole('region', { name: 'Simulated payment' }).getByLabel('Approve payment').check();
  await page.getByRole('button', { name: 'Place order' }).click();
  await expect(page).toHaveURL(ORDER_URL);
  const orderId = page.url().split('/').pop()!;
  await context.close();
  return orderId;
}

/** The number shown on one of the overview's order counters. */
async function counter(page: Page, label: string): Promise<number> {
  const item = page
    .getByRole('list', { name: 'Order counts' })
    .getByRole('listitem')
    .filter({ hasText: new RegExp(`^\\s*\\d+\\s*${label}\\s*$`) });
  return Number((await item.textContent())!.match(/\d+/)![0]);
}

test('the instructor view shows only a sign-in form until the instructor signs in', async ({ page }) => {
  await page.goto('/admin');

  await expect(page.getByRole('heading', { level: 1, name: 'Instructor sign-in' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Inventory' })).toHaveCount(0);
  await expect(page.getByRole('heading', { name: 'Recent orders' })).toHaveCount(0);

  await signIn(page, 'not-the-instructor-password');
  await expect(page.getByRole('alert')).toContainText('Username or password is incorrect.');
  await expect(page.getByRole('heading', { name: 'Inventory' })).toHaveCount(0);
});

test('a guest session cannot read orders or change stock', async ({ page }) => {
  await page.goto('/');
  const session = await (await page.request.get('/api/v1/session')).json();
  const products = await (await page.request.get('/api/v1/products')).json();

  const overview = await page.request.get('/api/v1/admin/orders');
  const change = await page.request.put(`/api/v1/admin/products/${products[0].id}/stock`, {
    data: { stock: 0 },
    headers: { 'X-CSRF-Token': session.csrf_token },
  });

  expect(overview.status()).toBe(401);
  expect(change.status()).toBe(401);
  await page.reload();
  await expect(page.getByRole('article').first()).not.toContainText('Sold out');
});

test('the instructor manages stock, sees orders, stays signed in on reload, and signs out', async ({
  page,
  browser,
}) => {
  const orderId = await guestBuys(browser, 'Helm Cap');

  await signIn(page);
  await expect(page.getByRole('heading', { level: 1, name: 'Instructor view' })).toBeVisible();
  const recent = page.getByRole('table', { name: 'Recent orders' });
  await expect(recent).toContainText(orderId.slice(0, 8).toUpperCase());
  const inventory = page.getByRole('table', { name: 'Inventory' });
  const helmCap = inventory.getByRole('row').filter({ hasText: 'Helm Cap' });
  await expect(helmCap.getByLabel('Stock for Helm Cap')).toHaveValue('29');

  await helmCap.getByLabel('Stock for Helm Cap').fill('3');
  await helmCap.getByRole('button', { name: 'Save' }).click();
  await expect(helmCap).toContainText('Saved');

  const shopper = await browser.newPage();
  await shopper.goto('/');
  await expect(product(shopper, 'Helm Cap')).toContainText('Only 3 left');
  await shopper.close();

  await page.reload();
  await expect(page.getByRole('heading', { level: 1, name: 'Instructor view' })).toBeVisible();

  await page.getByRole('button', { name: 'Sign out' }).click();
  await expect(page.getByRole('heading', { level: 1, name: 'Instructor sign-in' })).toBeVisible();
  await page.reload();
  await expect(page.getByRole('heading', { level: 1, name: 'Instructor sign-in' })).toBeVisible();
  expect((await page.request.get('/api/v1/admin/orders')).status()).toBe(401);
});

test('the overview shows a backlog building while no worker runs and draining after', async ({
  page,
  browser,
  fulfillment,
}) => {
  await signIn(page);
  await expect(page.getByRole('heading', { level: 1, name: 'Instructor view' })).toBeVisible();
  const queuedBefore = await counter(page, 'Queued');
  const fulfilledBefore = await counter(page, 'Fulfilled');

  await fulfillment.stop();
  await guestBuys(browser, 'Node Sticker Pack');
  await guestBuys(browser, 'YAML Notebook');

  await expect.poll(() => counter(page, 'Queued'), { timeout: 15_000 }).toBe(queuedBefore + 2);
  await expect(page.getByRole('table', { name: 'Recent orders' }).getByRole('row').nth(1)).toContainText('Queued');

  await fulfillment.start();
  await expect.poll(() => counter(page, 'Fulfilled'), { timeout: 30_000 }).toBe(fulfilledBefore + 2);
  expect(await counter(page, 'Queued')).toBe(queuedBefore);
});
