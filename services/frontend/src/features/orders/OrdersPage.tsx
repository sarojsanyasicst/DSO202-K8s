import { Link } from 'react-router';

import { api, call, useGuestSession, type Order } from '../../api';
import { formatDateTime, formatMoney, orderNumber, plural } from '../../format';
import { STAGES, isFinished, stageOf } from './status';
import { usePolling } from './usePolling';

export function OrdersPage() {
  const { withGuest, epoch } = useGuestSession();
  const { value: orders, error } = usePolling(
    () => withGuest(() => call(() => api.GET('/api/v1/orders'))),
    (loaded: Order[]) => loaded.every((order) => isFinished(stageOf(order))),
    epoch,
  );

  return (
    <>
      <div className="page-intro">
        <h1>Your orders</h1>
        <p className="muted">Orders placed from this browser session, newest first.</p>
      </div>
      {!orders ? (
        error ? (
          <div className="panel" role="alert">
            <p>Your orders could not be loaded. {error} The page keeps trying.</p>
          </div>
        ) : (
          <p className="loading">Loading your orders…</p>
        )
      ) : orders.length === 0 ? (
        <div className="panel empty">
          <p>You have not placed any orders yet.</p>
          <Link className="button" to="/">
            Browse the shop
          </Link>
        </div>
      ) : (
        <ul className="order-list" aria-label="Your orders">
          {orders.map((order) => {
            const stage = stageOf(order);
            const units = order.items.reduce((sum, item) => sum + item.quantity, 0);
            return (
              <li key={order.id} className="order-row">
                <Link to={`/orders/${order.id}`}>Order {orderNumber(order.id)}</Link>
                <span className={`badge badge-${stage}`}>{STAGES[stage].label}</span>
                <span className="muted">{formatDateTime(order.created_at)}</span>
                <span className="muted">{plural(units, 'item', 'items')}</span>
                <span className="order-total">{formatMoney(order.total_cents)}</span>
              </li>
            );
          })}
        </ul>
      )}
    </>
  );
}
