# Storefront

React and TypeScript storefront for CloudCart, built with Vite. It holds the shop (product grid, cart, simulated checkout), the guest's orders with live status and receipts, and the instructor view (sign-in, order backlog, stock levels).

## Layout

- `src/api.tsx`: the typed API client and the guest session. Types come from `src/api/schema.d.ts`, generated from the API's own OpenAPI document (`src/api/openapi.json`); run `make frontend-types` after changing the API. A backend unit test fails when the committed document no longer matches the API.
- `src/features/{catalog,cart,orders,admin}/`: one folder per screen group.
- `public/products/<sku>.svg`: product images, one per seeded SKU.
- `tests/`: Playwright browser tests (`shop`, `instructor`, `quality`) and their stack helpers.

## Commands

Run from `services/frontend` (Node 22.22 or newer):

```bash
npm ci
```

```bash
npm run build
```

`npm run dev` and `npm run preview` forward `/api` to `CLOUDCART_API_URL` (default `http://127.0.0.1:8000`) with the browser's `Host` header unchanged; the API refuses state changes whose `Origin` names a different host. `CLOUDCART_RELEASE_VERSION` at build time sets the storefront version shown in the footer (default `dev`); the footer also shows the API's `GET /api/v1/version`.

## Browser tests

From the repository root, with the disposable dependencies running:

```bash
make test-deps-up
```

```bash
make test-e2e
```

The run builds the storefront, serves it with `vite preview` on `http://localhost:14173`, recreates a `cloudcart_e2e` database, starts the API with its outbox publisher on port 18000, and runs a fulfillment worker that tests stop and restart. Narrow the run with `make test-e2e TEST=tests/shop.spec.ts`. Do not run it while backend integration tests run: both use the broker's `orders` queue.

## Behaviour worth knowing

- One `GET /api/v1/session` at a time bootstraps the guest. After a 401 or 403 the session is fetched again; only a different session (expired, or replaced in another tab) leads to one retry. Otherwise the refusal itself is shown. A shopper whose session expired gets a new, empty cart and never sees the previous guest's orders.
- Checkout sends a fresh `Idempotency-Key` per reviewed cart and payment choice, and resends it unchanged after a dropped connection or a server or gateway error (5xx), so a retry cannot order twice.
- Order pages poll every two seconds until the order is fulfilled or failed; the instructor view refreshes every three seconds.
