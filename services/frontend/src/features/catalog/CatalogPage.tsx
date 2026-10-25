import { useEffect } from 'react';

import type { Product } from '../../api';
import { formatMoney } from '../../format';
import { MAX_LINE_QUANTITY, stockLabel, useCart } from '../cart/CartProvider';

export function CatalogPage() {
  const { products, reload } = useCart();

  // Stock changes while shoppers browse; show the current numbers on every visit.
  useEffect(() => {
    void reload();
  }, [reload]);

  return (
    <>
      <div className="page-intro">
        <h1>Gear for cluster operators</h1>
        <p>Mugs, hoodies, and desk supplies for people who keep workloads running.</p>
      </div>
      {products.error && !products.value ? (
        <div className="panel" role="alert">
          <p>The catalog could not be loaded. {products.error}</p>
          <button type="button" className="button secondary" onClick={() => void reload()}>
            Try again
          </button>
        </div>
      ) : !products.value ? (
        <p className="loading">Loading products…</p>
      ) : (
        <ul className="product-grid">
          {products.value.map((product) => (
            <li key={product.id}>
              <ProductCard product={product} />
            </li>
          ))}
        </ul>
      )}
    </>
  );
}

function ProductCard({ product }: { product: Product }) {
  const { quantityOf, busy, addOne } = useCart();
  const inCart = quantityOf(product.id);
  const atLimit = inCart >= Math.min(MAX_LINE_QUANTITY, product.stock);
  const headingId = `product-${product.sku}`;

  return (
    <article className="product" aria-labelledby={headingId}>
      <div className="product-art">
        <img src={product.image_path} alt={product.name} width="320" height="240" />
      </div>
      <div className="product-body">
        <h2 id={headingId}>{product.name}</h2>
        <p className="product-description">{product.description}</p>
        <p className="product-price">{formatMoney(product.price_cents)}</p>
        <p className={product.stock <= 5 ? 'stock stock-low' : 'stock'}>{stockLabel(product.stock)}</p>
        <div className="product-actions">
          <button
            type="button"
            className="button"
            disabled={atLimit || busy.has(product.id)}
            onClick={() => void addOne(product)}
          >
            Add to cart
          </button>
          {inCart > 0 && <span className="in-cart">In your cart: {inCart}</span>}
        </div>
        {inCart > 0 && atLimit && product.stock > 0 && (
          <p className="hint">
            {inCart >= MAX_LINE_QUANTITY ? `Limit ${MAX_LINE_QUANTITY} per order.` : 'You have all the stock we hold.'}
          </p>
        )}
      </div>
    </article>
  );
}
