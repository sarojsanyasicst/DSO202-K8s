import { useEffect, useState, type FormEvent } from 'react';

import { ApiError, api, call, messageOf, type Product } from '../../api';
import { formatMoney } from '../../format';

/** The API's upper bound for one product's stock. */
const MAX_STOCK = 100_000;

type Props = { tick: number; csrfToken: string; onSessionEnded(): void };

export function InventoryTable({ tick, csrfToken, onSessionEnded }: Props) {
  const [products, setProducts] = useState<Product[] | null>(null);
  const [problem, setProblem] = useState<string | null>(null);

  useEffect(() => {
    let current = true;
    call(() => api.GET('/api/v1/products')).then(
      (loaded) => {
        if (!current) return;
        setProducts(loaded);
        setProblem(null);
      },
      (error: unknown) => current && setProblem(messageOf(error)),
    );
    return () => {
      current = false;
    };
  }, [tick]);

  return (
    <section className="admin-section" aria-labelledby="inventory-heading">
      <h2 id="inventory-heading">Inventory</h2>
      {problem && (
        <p className="warning" role="alert">
          Stock levels could not be refreshed: {problem}
        </p>
      )}
      {!products ? (
        <p className="loading">Loading stock levels…</p>
      ) : (
        <div className="table-scroll">
          <table aria-labelledby="inventory-heading">
            <thead>
              <tr>
                <th scope="col">Product</th>
                <th scope="col" className="wide-only">
                  SKU
                </th>
                <th scope="col" className="number">
                  Price
                </th>
                <th scope="col">Stock</th>
              </tr>
            </thead>
            <tbody>
              {products.map((product) => (
                <StockRow key={product.id} product={product} csrfToken={csrfToken} onSessionEnded={onSessionEnded} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

type RowProps = { product: Product; csrfToken: string; onSessionEnded(): void };

function StockRow({ product, csrfToken, onSessionEnded }: RowProps) {
  // While the instructor edits, refreshes must not overwrite what they are typing.
  const [draft, setDraft] = useState<string | null>(null);
  const [state, setState] = useState<{ kind: 'idle' | 'saving' | 'saved' } | { kind: 'error'; message: string }>({
    kind: 'idle',
  });
  const inputId = `stock-${product.sku}`;

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const stock = Number(draft ?? product.stock);
    setState({ kind: 'saving' });
    try {
      await call(() =>
        api.PUT('/api/v1/admin/products/{product_id}/stock', {
          params: { path: { product_id: product.id }, header: { 'X-CSRF-Token': csrfToken } },
          body: { stock },
        }),
      );
      setDraft(null);
      setState({ kind: 'saved' });
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        onSessionEnded();
        return;
      }
      setState({
        kind: 'error',
        message:
          error instanceof ApiError && error.status === 422
            ? `Enter a whole number from 0 to ${MAX_STOCK.toLocaleString('en-US')}.`
            : messageOf(error),
      });
    }
  }

  return (
    <tr>
      <th scope="row">{product.name}</th>
      <td className="sku wide-only">{product.sku}</td>
      <td className="number">{formatMoney(product.price_cents)}</td>
      <td>
        <form className="stock-form" onSubmit={(event) => void save(event)}>
          <input
            id={inputId}
            type="number"
            inputMode="numeric"
            min={0}
            max={MAX_STOCK}
            step={1}
            required
            aria-label={`Stock for ${product.name}`}
            value={draft ?? String(product.stock)}
            onChange={(event) => {
              setDraft(event.target.value);
              setState({ kind: 'idle' });
            }}
          />
          <button type="submit" className="button secondary small" disabled={state.kind === 'saving'}>
            Save
          </button>
          <span className="stock-state" role="status">
            {state.kind === 'saved' && 'Saved'}
            {state.kind === 'error' && state.message}
          </span>
        </form>
      </td>
    </tr>
  );
}
