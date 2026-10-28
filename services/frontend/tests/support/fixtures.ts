import { test as base, expect, type Page } from '@playwright/test';

import { FulfillmentWorker, resetCatalog } from './stack';

type TestFixtures = { catalog: void };
type WorkerFixtures = { fulfillment: FulfillmentWorker };

export const test = base.extend<TestFixtures, WorkerFixtures>({
  // One worker subprocess for the whole run; a test may stop it, and it is running again afterwards.
  fulfillment: [
    async ({}, use) => {
      const worker = new FulfillmentWorker();
      await worker.start();
      await use(worker);
      await worker.stop();
    },
    { scope: 'worker', auto: true },
  ],
  // Every test starts from the seeded stock and prices.
  catalog: [
    async ({ fulfillment }, use) => {
      resetCatalog();
      await use();
      await fulfillment.restoreDefault();
    },
    { auto: true },
  ],
});

export { expect };

export function product(page: Page, name: string) {
  return page.getByRole('article', { name });
}

/** Add `name` to a cart that does not hold it yet, `times` times, waiting for each change to show. */
export async function addToCart(page: Page, name: string, times = 1): Promise<void> {
  const card = product(page, name);
  for (let count = 1; count <= times; count++) {
    await card.getByRole('button', { name: 'Add to cart' }).click();
    await expect(card.getByText(`In your cart: ${count}`)).toBeVisible();
  }
}
