import { useEffect, useState } from 'react';

import { ApiError, api, call, messageOf, type AdminOrders } from '../../api';
import { formatDateTime, formatMoney, orderNumber } from '../../format';
import { STAGES, stageOf, type Stage } from '../orders/status';

type Props = { tick: number; onLoaded(): void; onSessionEnded(): void };

/** Counters in the order an order moves through them. */
const COUNTERS: { stage: Stage; count(overview: AdminOrders): number }[] = [
  { stage: 'waiting', count: (overview) => overview.publication_pending },
  { stage: 'queued', count: (overview) => overview.status_counts.accepted - overview.publication_pending },
  { stage: 'packing', count: (overview) => overview.status_counts.processing },
  { stage: 'fulfilled', count: (overview) => overview.status_counts.fulfilled },
  { stage: 'failed', count: (overview) => overview.status_counts.failed },
];

export function OrdersOverview({ tick, onLoaded, onSessionEnded }: Props) {
  const [overview, setOverview] = useState<AdminOrders | null>(null);
  const [problem, setProblem] = useState<string | null>(null);

  useEffect(() => {
    let current = true;
    call(() => api.GET('/api/v1/admin/orders')).then(
      (loaded) => {
        if (!current) return;
        setOverview(loaded);
        setProblem(null);
        onLoaded();
      },
      (error: unknown) => {
        if (!current) return;
        if (error instanceof ApiError && error.status === 401) onSessionEnded();
        else setProblem(messageOf(error));
      },
    );
    return () => {
      current = false;
    };
  }, [tick, onLoaded, onSessionEnded]);

  return (
    <section className="admin-section" aria-labelledby="orders-heading">
      <h2 id="orders-heading">Orders</h2>
      {problem && (
        <p className="warning" role="alert">
          The order overview could not be refreshed: {problem}
        </p>
      )}
      {!overview ? (
        <p className="loading">Loading orders…</p>
      ) : (
        <>
          <ul className="counters" aria-label="Order counts">
            {COUNTERS.map(({ stage, count }) => (
              <li key={stage} className={`counter counter-${stage}`}>
                <span className="counter-value">{count(overview)}</span>
                <span className="counter-label">{STAGES[stage].label}</span>
              </li>
            ))}
          </ul>
          <p className="muted small">
            Waiting to be queued: saved orders the shop has not yet handed to the fulfillment queue. Queued: orders in the
            queue that no worker has picked up.
          </p>
          <h3 id="recent-orders-heading">Recent orders</h3>
          {overview.orders.length === 0 ? (
            <p>No orders yet.</p>
          ) : (
            <div className="table-scroll">
              <table aria-labelledby="recent-orders-heading">
                <thead>
                  <tr>
                    <th scope="col">Order</th>
                    <th scope="col" className="wide-only">
                      Placed
                    </th>
                    <th scope="col">Status</th>
                    <th scope="col" className="number">
                      Attempts
                    </th>
                    <th scope="col" className="number">
                      Items
                    </th>
                    <th scope="col" className="number">
                      Total
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {overview.orders.map((order) => {
                    const stage = stageOf(order);
                    return (
                      <tr key={order.id}>
                        <th scope="row" title={order.id}>
                          {orderNumber(order.id)}
                        </th>
                        <td className="wide-only">{formatDateTime(order.created_at)}</td>
                        <td>
                          <span className={`badge badge-${stage}`}>{STAGES[stage].label}</span>
                        </td>
                        <td className="number">{order.fulfillment_attempts}</td>
                        <td className="number">{order.item_count}</td>
                        <td className="number">{formatMoney(order.total_cents)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </section>
  );
}
