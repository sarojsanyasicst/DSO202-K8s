import { addToCart, expect, product, test } from './support/fixtures';
import { API_RELEASE, STOREFRONT_RELEASE, WEB_PORT, expireGuestSessions, setStock } from './support/stack';

const ORDER_URL = /\/orders\/[0-9a-f-]{36}$/;
const FULFILLMENT_TIMEOUT = { timeout: 30_000 };

function cartLine(page: import('@playwright/test').Page, name: string) {
  return page.getByRole('list', { name: 'Cart items' }).getByRole('listitem').filter({ hasText: name });
}

async function placeOrder(page: import('@playwright/test').Page, payment: 'Approve payment' | 'Decline payment') {
  await page.getByRole('link', { name: /^Cart, / }).click();
  await expect(page.getByRole('heading', { level: 1, name: 'Your cart' })).toBeVisible();
  await page.getByRole('region', { name: 'Simulated payment' }).getByLabel(payment).check();
  await page.getByRole('button', { name: 'Place order' }).click();
}

function orderStatus(page: import('@playwright/test').Page) {
  return page.getByRole('region', { name: 'Order status' });
}

test('a guest browses, checks out, and sees the order fulfilled with a receipt', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('article')).toHaveCount(8);
  await expect(product(page, 'Kubernetes Mug')).toContainText('$14.99');
  await expect(product(page, 'Kubernetes Mug')).toContainText('40 in stock');
  await expect(product(page, 'Kubernetes Mug').getByRole('img')).toHaveAttribute('src', '/products/kube-mug.svg');

  await addToCart(page, 'Kubernetes Mug', 2);
  await addToCart(page, 'Helm Cap');
  await expect(page.getByRole('link', { name: 'Cart, 3 items' })).toBeVisible();

  await page.getByRole('link', { name: 'Cart, 3 items' }).click();
  await expect(cartLine(page, 'Kubernetes Mug').getByLabel('Quantity')).toHaveValue('2');
  await expect(page.getByRole('region', { name: 'Order summary' })).toContainText('$51.97');
  const payment = page.getByRole('region', { name: 'Simulated payment' });
  await expect(payment).toContainText('No real money');
  await payment.getByLabel('Approve payment').check();
  await page.getByRole('button', { name: 'Place order' }).click();

  await expect(page).toHaveURL(ORDER_URL);
  await expect(page.getByRole('link', { name: 'Cart, 0 items' })).toBeVisible();
  await expect(orderStatus(page).getByRole('heading', { name: 'Fulfilled' })).toBeVisible(FULFILLMENT_TIMEOUT);
  await expect(page.locator('[aria-current="step"]')).toContainText('Dispatched');
  await expect(page.getByRole('region', { name: 'Items' })).toContainText('Kubernetes Mug');

  await page.getByRole('link', { name: 'View receipt' }).click();
  await expect(page.getByRole('heading', { level: 1, name: 'Receipt' })).toBeVisible();
  const receipt = page.getByRole('main');
  await expect(receipt).toContainText('Kubernetes Mug');
  await expect(receipt).toContainText('Helm Cap');
  await expect(receipt).toContainText('$51.97');
  await expect(receipt).toContainText('No payment was taken');

  await page.getByRole('link', { name: 'Orders', exact: true }).click();
  const orders = page.getByRole('list', { name: 'Your orders' }).getByRole('listitem');
  await expect(orders).toHaveCount(1);
  await expect(orders.first()).toContainText('Fulfilled');
  await expect(orders.first()).toContainText('$51.97');
});

test('the cart survives a reload and a second tab', async ({ page, context }) => {
  await page.goto('/');
  await addToCart(page, 'Pod Hoodie', 2);

  await page.reload();
  await expect(product(page, 'Pod Hoodie').getByText('In your cart: 2')).toBeVisible();

  const secondTab = await context.newPage();
  await secondTab.goto('/cart');
  await expect(cartLine(secondTab, 'Pod Hoodie').getByLabel('Quantity')).toHaveValue('2');
  await cartLine(secondTab, 'Pod Hoodie').getByLabel('Quantity').selectOption('3');
  await expect(secondTab.getByRole('link', { name: 'Cart, 3 items' })).toBeVisible();

  await page.reload();
  await expect(product(page, 'Pod Hoodie').getByText('In your cart: 3')).toBeVisible();
});

test('an order waits visibly in the queue while no worker runs, then completes', async ({ page, fulfillment }) => {
  await fulfillment.stop();
  await page.goto('/');
  await addToCart(page, 'YAML Notebook');
  await placeOrder(page, 'Approve payment');

  await expect(page).toHaveURL(ORDER_URL);
  await expect(orderStatus(page).getByRole('heading', { name: 'Queued for packing' })).toBeVisible();
  await expect(page.locator('[aria-current="step"]')).toContainText('Queued');
  // Several polls later the order is still queued: nothing is consuming the queue.
  await page.waitForTimeout(5_000);
  await expect(orderStatus(page).getByRole('heading', { name: 'Queued for packing' })).toBeVisible();

  await page.getByRole('link', { name: 'Orders', exact: true }).click();
  await expect(page.getByRole('list', { name: 'Your orders' }).getByRole('listitem').first()).toContainText('Queued');
  await page.getByRole('list', { name: 'Your orders' }).getByRole('link').first().click();

  await fulfillment.start();
  await expect(orderStatus(page).getByRole('heading', { name: 'Fulfilled' })).toBeVisible(FULFILLMENT_TIMEOUT);
});

test('an order still waiting for the queue says so', async ({ page, fulfillment }) => {
  await fulfillment.stop();
  // The publisher cannot be paused from a test, so this display check reports the real order as unpublished.
  await page.route(/\/api\/v1\/orders\/[0-9a-f-]{36}$/, async (route) => {
    const response = await route.fetch();
    await route.fulfill({ response, json: { ...(await response.json()), publication_pending: true } });
  });
  await page.goto('/');
  await addToCart(page, 'Cluster Socks');
  await placeOrder(page, 'Approve payment');

  await expect(orderStatus(page).getByRole('heading', { name: 'Waiting to be queued' })).toBeVisible();
  await expect(page.locator('[aria-current="step"]')).toContainText('Placed');
});

test('a failed order says its items went back on the shelf', async ({ page, fulfillment }) => {
  await fulfillment.stop();
  await fulfillment.start({ failingAttempts: 4 });
  await page.goto('/');
  await addToCart(page, 'Container Tote', 2);
  await placeOrder(page, 'Approve payment');

  await expect(orderStatus(page).getByRole('heading', { name: 'Could not be fulfilled' })).toBeVisible(
    FULFILLMENT_TIMEOUT,
  );
  await expect(orderStatus(page)).toContainText('back on the shelf');
  await expect(page.getByRole('link', { name: 'View receipt' })).toHaveCount(0);
  await page.getByRole('link', { name: 'Shop', exact: true }).click();
  await expect(product(page, 'Container Tote')).toContainText('35 in stock');
});

test('stale stock stops checkout with a message and keeps the cart', async ({ page }) => {
  await page.goto('/');
  await addToCart(page, 'GitOps Poster', 3);
  setStock('gitops-poster', 1);

  await placeOrder(page, 'Approve payment');

  await expect(page.getByRole('alert')).toContainText('Not enough stock for: GitOps Poster');
  await expect(page).toHaveURL(/\/cart$/);
  await expect(cartLine(page, 'GitOps Poster')).toContainText('Only 1 left');

  await cartLine(page, 'GitOps Poster').getByLabel('Quantity').selectOption('1');
  await expect(page.getByRole('link', { name: 'Cart, 1 item' })).toBeVisible();
  await page.getByRole('button', { name: 'Place order' }).click();
  await expect(page).toHaveURL(ORDER_URL);
});

test('a declined simulated payment keeps the cart and places no order', async ({ page }) => {
  await page.goto('/');
  await addToCart(page, 'Cluster Socks');

  await placeOrder(page, 'Decline payment');

  await expect(page.getByRole('alert')).toContainText('The simulated payment was declined');
  await expect(page.getByRole('alert')).toContainText('cart is unchanged');
  await expect(cartLine(page, 'Cluster Socks').getByLabel('Quantity')).toHaveValue('1');
  await page.getByRole('link', { name: 'Orders', exact: true }).click();
  await expect(page.getByText('You have not placed any orders yet.')).toBeVisible();
});

test('retrying after a dropped connection places exactly one order', async ({ page }) => {
  await page.goto('/');
  await addToCart(page, 'Node Sticker Pack');
  let dropped = false;
  await page.route('**/api/v1/orders', async (route) => {
    if (route.request().method() === 'POST' && !dropped) {
      dropped = true;
      await route.fetch(); // the API accepts the order, but its answer never reaches the page
      await route.abort('connectionfailed');
    } else {
      await route.continue();
    }
  });

  await placeOrder(page, 'Approve payment');
  await expect(page.getByRole('alert')).toContainText('connection dropped');
  await page.getByRole('button', { name: 'Retry order' }).click();

  await expect(page).toHaveURL(ORDER_URL);
  await page.getByRole('link', { name: 'Orders', exact: true }).click();
  await expect(page.getByRole('list', { name: 'Your orders' }).getByRole('listitem')).toHaveCount(1);
});

test('retrying after a gateway error places exactly one order', async ({ page }) => {
  await page.goto('/');
  await addToCart(page, 'YAML Notebook');
  let failed = false;
  await page.route('**/api/v1/orders', async (route) => {
    if (route.request().method() === 'POST' && !failed) {
      failed = true;
      await route.fetch(); // the API accepts the order, then the gateway loses its answer
      await route.fulfill({ status: 502, contentType: 'text/plain', body: 'Bad Gateway' });
    } else {
      await route.continue();
    }
  });

  await placeOrder(page, 'Approve payment');
  await expect(page.getByRole('alert')).toContainText('may already be placed');
  await page.getByRole('button', { name: 'Retry order' }).click();

  await expect(page).toHaveURL(ORDER_URL);
  await page.getByRole('link', { name: 'Orders', exact: true }).click();
  await expect(page.getByRole('list', { name: 'Your orders' }).getByRole('listitem')).toHaveCount(1);
});

test('a refused change shows the refusal, not a new session', async ({ page }) => {
  await page.goto('/');
  await addToCart(page, 'Helm Cap');
  await page.getByRole('link', { name: /^Cart, / }).click();
  // What a gateway that rewrites the Host header causes: same-origin reads work, every change is refused.
  const refuseOnce = (method: string) => {
    let refused = false;
    return async (route: import('@playwright/test').Route) => {
      if (route.request().method() === method && !refused) {
        refused = true;
        await route.fulfill({ status: 403, json: { detail: 'Cross-origin request refused.' } });
      } else {
        await route.continue();
      }
    };
  };
  await page.route('**/api/v1/cart/items/*', refuseOnce('PUT'));
  await page.route('**/api/v1/orders', refuseOnce('POST'));

  await cartLine(page, 'Helm Cap').getByLabel('Quantity').selectOption('2');
  await expect(page.getByRole('alert')).toContainText('Cross-origin request refused.');
  await expect(cartLine(page, 'Helm Cap').getByLabel('Quantity')).toHaveValue('1');

  await page.getByRole('button', { name: 'Place order' }).click();
  await expect(page.getByRole('region', { name: 'Order summary' }).getByRole('alert')).toContainText(
    'Cross-origin request refused.',
  );
  await expect(page.getByText('Your previous session ended')).toHaveCount(0);
  await expect(page).toHaveURL(/\/cart$/);
});

test('an expired session starts fresh without showing the previous guest anything', async ({ page }) => {
  await page.goto('/');
  await addToCart(page, 'Container Tote');
  await placeOrder(page, 'Approve payment');
  await expect(page).toHaveURL(ORDER_URL);
  const previousOrder = page.url();
  await page.getByRole('link', { name: 'Shop', exact: true }).click();
  await addToCart(page, 'Helm Cap');

  expireGuestSessions();
  await page.reload();

  await expect(page.getByRole('link', { name: 'Cart, 0 items' })).toBeVisible();
  await expect(product(page, 'Helm Cap').getByText(/In your cart/)).toHaveCount(0);
  await page.getByRole('link', { name: 'Orders', exact: true }).click();
  await expect(page.getByText('You have not placed any orders yet.')).toBeVisible();
  await page.goto(previousOrder);
  await expect(page.getByRole('heading', { level: 1, name: 'Order not found' })).toBeVisible();
  await page.getByRole('link', { name: 'Shop', exact: true }).click();
  await addToCart(page, 'Helm Cap');
});

test('a session that expires while the page is open recovers on the next action', async ({ page }) => {
  await page.goto('/');
  await addToCart(page, 'Kubernetes Mug');

  expireGuestSessions();
  await addToCart(page, 'Pod Hoodie');

  await expect(page.getByRole('status').filter({ hasText: 'Your previous session ended' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Cart, 1 item' })).toBeVisible();
  await expect(product(page, 'Kubernetes Mug').getByText(/In your cart/)).toHaveCount(0);
});

test('a cross-site link cannot replace the guest session', async ({ page }) => {
  await page.goto('/');
  await addToCart(page, 'Kubernetes Mug');
  await page.route('http://cross-site.test/**', (route) =>
    route.fulfill({
      contentType: 'text/html',
      body: `<a href="http://localhost:${WEB_PORT}/api/v1/session">Claim your prize</a>`,
    }),
  );

  await page.goto('http://cross-site.test/');
  await page.getByRole('link', { name: 'Claim your prize' }).click();
  await expect(page.locator('body')).toContainText('Cross-site request refused');

  await page.goto('/');
  await expect(product(page, 'Kubernetes Mug').getByText('In your cart: 1')).toBeVisible();
});

test('the footer shows the storefront and API versions', async ({ page }) => {
  await page.goto('/');

  const footer = page.getByRole('contentinfo');
  await expect(footer).toContainText(`Storefront ${STOREFRONT_RELEASE}`);
  await expect(footer).toContainText(`API ${API_RELEASE}`);
});
