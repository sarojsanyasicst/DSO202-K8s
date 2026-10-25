import AxeBuilder from '@axe-core/playwright';
import type { Page } from '@playwright/test';

import { addToCart, expect, product, test } from './support/fixtures';
import { ADMIN_PASSWORD } from './support/stack';

const ORDER_URL = /\/orders\/[0-9a-f-]{36}$/;
const NARROW = { width: 360, height: 780 };

/** Visit every screen once (cart, order, receipt, orders, instructor) and run `check` on each. */
async function visitEveryScreen(page: Page, check: (screen: string) => Promise<void>): Promise<void> {
  await page.goto('/');
  await addToCart(page, 'Kubernetes Mug');
  await check('shop');

  await page.getByRole('link', { name: /^Cart, / }).click();
  await expect(page.getByRole('list', { name: 'Cart items' })).toBeVisible();
  await check('cart');

  await page.getByRole('region', { name: 'Simulated payment' }).getByLabel('Approve payment').check();
  await page.getByRole('button', { name: 'Place order' }).click();
  await expect(page).toHaveURL(ORDER_URL);
  await expect(page.getByRole('region', { name: 'Order status' })).toBeVisible();
  await check('order (in progress)');
  await expect(page.getByRole('region', { name: 'Order status' }).getByRole('heading', { name: 'Fulfilled' })).toBeVisible(
    { timeout: 30_000 },
  );
  await check('order (fulfilled)');

  await page.getByRole('link', { name: 'View receipt' }).click();
  await expect(page.getByRole('heading', { level: 1, name: 'Receipt' })).toBeVisible();
  await check('receipt');

  await page.getByRole('link', { name: 'Orders', exact: true }).click();
  await expect(page.getByRole('list', { name: 'Your orders' })).toBeVisible();
  await check('orders');

  await page.goto('/cart');
  await expect(page.getByText('Your cart is empty.')).toBeVisible();
  await check('empty cart');

  await page.goto('/admin');
  await expect(page.getByRole('heading', { level: 1, name: 'Instructor sign-in' })).toBeVisible();
  await check('instructor sign-in');

  await page.getByLabel('Username').fill('instructor');
  await page.getByLabel('Password').fill(ADMIN_PASSWORD);
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page.getByRole('table', { name: 'Inventory' })).toBeVisible();
  await check('instructor view');
}

test('every screen passes automated WCAG 2.1 AA checks', async ({ page }) => {
  const failures: string[] = [];
  await visitEveryScreen(page, async (screen) => {
    const results = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']).analyze();
    for (const violation of results.violations) {
      failures.push(`${screen}: ${violation.id} (${violation.impact}) ${violation.nodes.map((node) => node.target).join(', ')}`);
    }
  });

  expect(failures).toEqual([]);
});

test('every screen fits a narrow phone screen without sideways scrolling', async ({ page }) => {
  await page.setViewportSize(NARROW);
  const overflowing: string[] = [];
  await visitEveryScreen(page, async (screen) => {
    const width = await page.evaluate(() => document.documentElement.scrollWidth);
    if (width <= NARROW.width) return;
    // Name the innermost elements that stick out, so a failure says what to fix.
    const culprits = await page.evaluate((limit) => {
      const wide = [...document.querySelectorAll('body *')].filter(
        (element) => element.getBoundingClientRect().right > limit + 0.5,
      );
      return wide
        .filter((element) => !wide.some((other) => other !== element && element.contains(other)))
        .slice(0, 4)
        .map((element) => `${element.tagName.toLowerCase()}.${element.className} "${element.textContent?.slice(0, 30)}"`);
    }, NARROW.width);
    overflowing.push(`${screen}: ${width}px (${culprits.join('; ')})`);
  });

  expect(overflowing).toEqual([]);
});

test('a shopper can skip to the products and add one using only the keyboard', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('article')).toHaveCount(8);

  await page.keyboard.press('Tab');
  await expect(page.getByRole('link', { name: 'Skip to content' })).toBeFocused();
  await page.keyboard.press('Enter');
  const firstAdd = product(page, 'Cluster Socks').getByRole('button', { name: 'Add to cart' });
  for (let presses = 0; presses < 5 && !(await firstAdd.evaluate((element) => element === document.activeElement)); presses++) {
    await page.keyboard.press('Tab');
  }
  await expect(firstAdd).toBeFocused();
  await page.keyboard.press('Enter');

  await expect(product(page, 'Cluster Socks').getByText('In your cart: 1')).toBeVisible();
});
