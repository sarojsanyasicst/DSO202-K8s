import { Link, useParams } from 'react-router';

import { api, call, useGuestSession, type Order, type OrderItem } from '../../api';
import { formatDateTime, formatMoney, orderNumber } from '../../format';
import { OrderRoute } from './OrderRoute';
import { STAGES, isFinished, stageOf } from './status';
import { usePolling } from './usePolling';

export function OrderPage() {
  const { orderId = '' } = useParams();
  const { withGuest, epoch } = useGuestSession();
  const { value: order, notFound, error } = usePolling(
    () => withGuest(() => call(() => api.GET('/api/v1/orders/{order_id}', { params: { path: { order_id: orderId } } }))),
    (loaded: Order) => isFinished(stageOf(loaded)),
    `${orderId}:${epoch}`,
  );

  if (notFound) return <OrderNotFound />;
  if (!order) {
    return error ? (
      <div className="panel" role="alert">
        <p>This order could not be loaded. {error} The page keeps trying.</p>
      </div>
    ) : (
      <p className="loading">Loading your order…</p>
    );
  }

  const stage = stageOf(order);
  const { headline, detail } = STAGES[stage];
  return (
    <>
      <div className="page-intro">
        <h1>Order {orderNumber(order.id)}</h1>
        <p className="muted">Placed {formatDateTime(order.created_at)}</p>
      </div>
      <div className="order-layout">
        <section className={`parcel parcel-${stage}`} aria-labelledby="order-status-heading">
          <h2 id="order-status-heading" className="visually-hidden">
            Order status
          </h2>
          <div aria-live="polite">
            <h3 className="status-headline">
              {headline}
            </h3>
            <p>{detail}</p>
          </div>
          <OrderRoute stage={stage} />
          {!isFinished(stage) && (
            <p className="muted small">This page checks for updates every two seconds.</p>
          )}
          {error && <p className="warning">Connection trouble: {error} Still trying.</p>}
          {order.receipt_available && (
            <Link className="button" to={`/orders/${order.id}/receipt`}>
              View receipt
            </Link>
          )}
        </section>
        <ItemsTable items={order.items} totalCents={order.total_cents} />
      </div>
    </>
  );
}

export function ItemsTable({ items, totalCents }: { items: OrderItem[]; totalCents: number }) {
  return (
    <section className="items" aria-labelledby="items-heading">
      <h2 id="items-heading">Items</h2>
      <div className="items-table">
        <table>
          <thead>
            <tr>
              <th scope="col">Product</th>
              <th scope="col" className="number">
                <span aria-hidden="true">Qty</span>
                <span className="visually-hidden">Quantity</span>
              </th>
              <th scope="col" className="number">
                Price
              </th>
              <th scope="col" className="number">
                Amount
              </th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <tr key={item.product_id}>
                <th scope="row">{item.name}</th>
                <td className="number">{item.quantity}</td>
                <td className="number">{formatMoney(item.unit_price_cents)}</td>
                <td className="number">{formatMoney(item.unit_price_cents * item.quantity)}</td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr>
              <th scope="row" colSpan={3}>
                Total
              </th>
              <td className="number">{formatMoney(totalCents)}</td>
            </tr>
          </tfoot>
        </table>
      </div>
    </section>
  );
}

function OrderNotFound() {
  return (
    <div className="page-intro">
      <h1>Order not found</h1>
      <p>This shop has no order with that number for your session. Orders belong to the browser session that placed them.</p>
      <p>
        <Link to="/orders">See your orders</Link>
      </p>
    </div>
  );
}
