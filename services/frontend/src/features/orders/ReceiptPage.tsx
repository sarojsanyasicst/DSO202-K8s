import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router';

import { ApiError, api, call, messageOf, useGuestSession, type Receipt } from '../../api';
import { formatDateTime, orderNumber } from '../../format';
import { ItemsTable } from './OrderPage';

export function ReceiptPage() {
  const { orderId = '' } = useParams();
  const { withGuest, epoch } = useGuestSession();
  const [receipt, setReceipt] = useState<Receipt | null>(null);
  const [problem, setProblem] = useState<string | null>(null);

  useEffect(() => {
    let current = true;
    setReceipt(null);
    setProblem(null);
    withGuest(() =>
      call(() => api.GET('/api/v1/orders/{order_id}/receipt', { params: { path: { order_id: orderId } } })),
    ).then(
      (loaded) => current && setReceipt(loaded),
      (error: unknown) => {
        if (!current) return;
        const missing = error instanceof ApiError && (error.status === 404 || error.status === 422);
        setProblem(missing ? 'There is no receipt for this order yet.' : messageOf(error));
      },
    );
    return () => {
      current = false;
    };
  }, [orderId, epoch, withGuest]);

  if (problem) {
    return (
      <div className="page-intro">
        <h1>Receipt not available</h1>
        <p>{problem}</p>
        <p>
          <Link to={`/orders/${orderId}`}>Back to the order</Link>
        </p>
      </div>
    );
  }
  if (!receipt) return <p className="loading">Loading the receipt…</p>;

  return (
    <article className="receipt" aria-labelledby="receipt-heading">
      <div className="page-intro">
        <h1 id="receipt-heading">Receipt</h1>
        <dl className="receipt-facts">
          <dt>Order</dt>
          <dd>{orderNumber(receipt.order_id)}</dd>
          <dt>Receipt number</dt>
          <dd>{orderNumber(receipt.id)}</dd>
          <dt>Issued</dt>
          <dd>{formatDateTime(receipt.issued_at)}</dd>
        </dl>
      </div>
      <ItemsTable items={receipt.items} totalCents={receipt.total_cents} />
      <p className="simulated-note">Simulated purchase. No payment was taken and nothing will be delivered.</p>
      <p className="receipt-actions">
        <button type="button" className="button secondary" onClick={() => window.print()}>
          Print receipt
        </button>
        <Link to={`/orders/${receipt.order_id}`}>Back to the order</Link>
      </p>
    </article>
  );
}
