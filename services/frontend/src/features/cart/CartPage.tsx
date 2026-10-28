import { useEffect, useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router';

import {
  ApiError,
  ConnectionError,
  SessionRenewedError,
  api,
  call,
  messageOf,
  newIdempotencyKey,
  useGuestSession,
  type Cart,
  type Product,
} from '../../api';
import { formatMoney } from '../../format';
import { MAX_LINE_QUANTITY, useCart } from './CartProvider';

const QUANTITIES = Array.from({ length: MAX_LINE_QUANTITY }, (_, index) => index + 1);

export function CartPage() {
  const { cart, products, reload } = useCart();

  useEffect(() => {
    void reload();
  }, [reload]);

  const byId = new Map((products.value ?? []).map((product) => [product.id, product]));

  return (
    <>
      <div className="page-intro">
        <h1>Your cart</h1>
      </div>
      {!cart.value ? (
        cart.error ? (
          <div className="panel" role="alert">
            <p>Your cart could not be loaded. {cart.error}</p>
            <button type="button" className="button secondary" onClick={() => void reload()}>
              Try again
            </button>
          </div>
        ) : (
          <p className="loading">Loading your cart…</p>
        )
      ) : cart.value.items.length === 0 ? (
        <div className="panel empty">
          <p>Your cart is empty.</p>
          <Link className="button" to="/">
            Browse the shop
          </Link>
        </div>
      ) : (
        <div className="cart-layout">
          <ul className="cart-lines" aria-label="Cart items">
            {cart.value.items.map((item) => (
              <CartLine
                key={item.product_id}
                productId={item.product_id}
                quantity={item.quantity}
                unitPriceCents={item.unit_price_cents}
                product={byId.get(item.product_id)}
              />
            ))}
          </ul>
          <Summary cart={cart.value} />
        </div>
      )}
    </>
  );
}

type LineProps = { productId: string; quantity: number; unitPriceCents: number; product: Product | undefined };

function CartLine({ productId, quantity, unitPriceCents, product }: LineProps) {
  const { busy, setQuantity, remove } = useCart();
  const name = product?.name ?? 'Product';
  const selectId = `quantity-${productId}`;
  const shortBy = product && quantity > product.stock;

  return (
    <li className="cart-line">
      {product && <img src={product.image_path} alt="" width="96" height="72" />}
      <div className="cart-line-main">
        <h2>{name}</h2>
        <p className="muted">{formatMoney(unitPriceCents)} each</p>
        {shortBy && (
          <p className="warning">{product.stock === 0 ? 'Sold out' : `Only ${product.stock} left`}: lower the quantity.</p>
        )}
      </div>
      <div className="cart-line-controls">
        <label htmlFor={selectId}>Quantity</label>
        <select
          id={selectId}
          value={quantity}
          disabled={busy.has(productId)}
          onChange={(event) => void setQuantity(productId, Number(event.target.value))}
        >
          {QUANTITIES.map((value) => (
            <option key={value} value={value}>
              {value}
            </option>
          ))}
        </select>
        <button
          type="button"
          className="button link"
          disabled={busy.has(productId)}
          onClick={() => void remove(productId)}
        >
          Remove
        </button>
      </div>
      <p className="cart-line-total">{formatMoney(unitPriceCents * quantity)}</p>
    </li>
  );
}

type Payment = 'approved' | 'declined';
type Attempt = { key: string; cartVersion: number; payment: Payment };
type Problem = { message: string; retryable: boolean };

function Summary({ cart }: { cart: Cart }) {
  const { withGuest } = useGuestSession();
  const { reload } = useCart();
  const navigate = useNavigate();
  const [payment, setPayment] = useState<Payment>('approved');
  const [placing, setPlacing] = useState(false);
  const [problem, setProblem] = useState<Problem | null>(null);
  // One Idempotency-Key per checkout of one reviewed cart; a retry after a dropped connection resends it.
  const attempt = useRef<Attempt | null>(null);

  async function placeOrder(retrying: boolean) {
    let current = attempt.current;
    if (!retrying || !current) {
      if (!current || current.cartVersion !== cart.version || current.payment !== payment) {
        current = { key: newIdempotencyKey(), cartVersion: cart.version, payment };
      }
    }
    attempt.current = current;
    const { key, cartVersion, payment: outcome } = current;
    setPlacing(true);
    setProblem(null);
    try {
      const order = await withGuest(
        (csrfToken) =>
          call(() =>
            api.POST('/api/v1/orders', {
              params: { header: { 'Idempotency-Key': key, 'X-CSRF-Token': csrfToken } },
              body: { cart_version: cartVersion, payment_outcome: outcome },
            }),
          ),
        { retry: false },
      );
      attempt.current = null;
      await reload();
      navigate(`/orders/${order.id}`);
    } catch (error) {
      // No answer, or a server-side failure (including a gateway's 502/503/504 when an API Pod goes
      // away mid-request): the order may exist already. Only a retry with the same key can tell
      // without ordering twice.
      if (error instanceof ConnectionError || (error instanceof ApiError && error.status >= 500)) {
        setProblem({
          message:
            error instanceof ConnectionError
              ? 'The connection dropped before the shop answered. Your order may already be placed: retry to finish it safely.'
              : 'The shop could not confirm your order. It may already be placed: retry to finish it safely.',
          retryable: true,
        });
        return;
      }
      attempt.current = null;
      if (error instanceof ApiError && error.status === 402) {
        setProblem({
          message: 'The simulated payment was declined. Nothing was charged and your cart is unchanged.',
          retryable: false,
        });
      } else if (error instanceof ApiError && error.status === 409) {
        setProblem({ message: `${error.message} Your cart has been refreshed.`, retryable: false });
        await reload();
      } else if (error instanceof SessionRenewedError) {
        setProblem({ message: error.message, retryable: false });
      } else {
        setProblem({ message: messageOf(error), retryable: false });
      }
    } finally {
      setPlacing(false);
    }
  }

  return (
    <section className="summary" aria-labelledby="summary-heading">
      <h2 id="summary-heading">Order summary</h2>
      <dl className="totals">
        <dt>Items</dt>
        <dd>{cart.items.reduce((sum, item) => sum + item.quantity, 0)}</dd>
        <dt>Total</dt>
        <dd className="total">{formatMoney(cart.total_cents)}</dd>
      </dl>
      <section className="simulated" aria-labelledby="payment-heading">
        <h2 id="payment-heading">Simulated payment</h2>
        <p>No real money moves in this practice shop. Choose how the pretend payment ends.</p>
        <fieldset>
          <legend>Payment result</legend>
          <label className="choice">
            <input
              type="radio"
              name="payment"
              value="approved"
              checked={payment === 'approved'}
              onChange={() => setPayment('approved')}
            />
            Approve payment
          </label>
          <label className="choice">
            <input
              type="radio"
              name="payment"
              value="declined"
              checked={payment === 'declined'}
              onChange={() => setPayment('declined')}
            />
            Decline payment
          </label>
        </fieldset>
      </section>
      {problem && (
        <div className="problem" role="alert">
          <p>{problem.message}</p>
          {problem.retryable && (
            <button type="button" className="button" disabled={placing} onClick={() => void placeOrder(true)}>
              Retry order
            </button>
          )}
        </div>
      )}
      <button type="button" className="button primary" disabled={placing} onClick={() => void placeOrder(false)}>
        {placing ? 'Placing order…' : 'Place order'}
      </button>
    </section>
  );
}
