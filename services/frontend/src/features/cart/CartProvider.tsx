// The catalog and the guest's cart, shared by the shop, the cart page, and the header badge.
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';

import { api, call, messageOf, useGuestSession, type Cart, type Product } from '../../api';

/** Most units of one product a cart line can hold (the API's limit). */
export const MAX_LINE_QUANTITY = 10;

type Loadable<T> = { value: T | null; error: string | null };

type CartContextValue = {
  products: Loadable<Product[]>;
  cart: Loadable<Cart>;
  /** Units in the cart. */
  count: number;
  quantityOf(productId: string): number;
  /** Product ids with a change on the way. */
  busy: ReadonlySet<string>;
  /** The last failed cart change, until the next change starts. */
  changeError: string | null;
  addOne(product: Product): Promise<void>;
  setQuantity(productId: string, quantity: number): Promise<void>;
  remove(productId: string): Promise<void>;
  reload(): Promise<void>;
};

const CartContext = createContext<CartContextValue | null>(null);

export function CartProvider({ children }: { children: ReactNode }) {
  const { withGuest, epoch } = useGuestSession();
  const [products, setProducts] = useState<Loadable<Product[]>>({ value: null, error: null });
  const [cart, setCartState] = useState<Loadable<Cart>>({ value: null, error: null });
  const [busy, setBusy] = useState<ReadonlySet<string>>(new Set());
  const [changeError, setChangeError] = useState<string | null>(null);
  // The latest cart, for changes computed from it (adding one more unit).
  const latestCart = useRef<Cart | null>(null);

  // Answers can arrive out of order (a reload racing a change); a cart's version only grows,
  // so an older version of the same cart never replaces a newer one.
  const setCart = useCallback((value: Cart) => {
    const latest = latestCart.current;
    if (latest && latest.id === value.id && latest.version > value.version) return;
    latestCart.current = value;
    setCartState({ value, error: null });
  }, []);

  const fetchCart = useCallback(
    () => withGuest(() => call(() => api.GET('/api/v1/cart'))),
    [withGuest],
  );

  const reload = useCallback(async () => {
    const [productsResult, cartResult] = await Promise.allSettled([
      call(() => api.GET('/api/v1/products')),
      fetchCart(),
    ]);
    setProducts(
      productsResult.status === 'fulfilled'
        ? { value: productsResult.value, error: null }
        : { value: null, error: messageOf(productsResult.reason) },
    );
    if (cartResult.status === 'fulfilled') setCart(cartResult.value);
    else setCartState((previous) => ({ value: previous.value, error: messageOf(cartResult.reason) }));
  }, [fetchCart, setCart]);

  // Load on start, and again whenever the shopper becomes a different guest.
  useEffect(() => {
    latestCart.current = null;
    setCartState({ value: null, error: null });
    void reload();
  }, [epoch, reload]);

  const change = useCallback(
    async (productId: string, request: (csrfToken: string, renewed: boolean) => Promise<Cart>) => {
      setBusy((ids) => new Set(ids).add(productId));
      setChangeError(null);
      try {
        setCart(await withGuest(request));
      } catch (error) {
        setChangeError(messageOf(error));
        void reload();
      } finally {
        setBusy((ids) => {
          const next = new Set(ids);
          next.delete(productId);
          return next;
        });
      }
    },
    [withGuest, reload, setCart],
  );

  const putQuantity = useCallback(
    (productId: string, quantity: number, csrfToken: string) =>
      call(() =>
        api.PUT('/api/v1/cart/items/{product_id}', {
          params: { path: { product_id: productId }, header: { 'X-CSRF-Token': csrfToken } },
          body: { quantity },
        }),
      ),
    [],
  );

  const addOne = useCallback(
    (product: Product) =>
      change(product.id, async (csrfToken, renewed) => {
        // After a new session starts, count from the new (empty) cart, not the old one.
        const current = renewed ? await fetchCart() : latestCart.current;
        const quantity = (current?.items.find((item) => item.product_id === product.id)?.quantity ?? 0) + 1;
        return putQuantity(product.id, quantity, csrfToken);
      }),
    [change, fetchCart, putQuantity],
  );

  const setQuantity = useCallback(
    (productId: string, quantity: number) =>
      change(productId, async (csrfToken, renewed) => {
        // A renewed session has an empty cart: the line being edited no longer exists.
        if (renewed) return fetchCart();
        return putQuantity(productId, quantity, csrfToken);
      }),
    [change, fetchCart, putQuantity],
  );

  const remove = useCallback(
    (productId: string) =>
      change(productId, async (csrfToken, renewed) => {
        if (renewed) return fetchCart();
        return call(() =>
          api.DELETE('/api/v1/cart/items/{product_id}', {
            params: { path: { product_id: productId }, header: { 'X-CSRF-Token': csrfToken } },
          }),
        );
      }),
    [change, fetchCart],
  );

  const value = useMemo<CartContextValue>(() => {
    const items = cart.value?.items ?? [];
    return {
      products,
      cart,
      count: items.reduce((sum, item) => sum + item.quantity, 0),
      quantityOf: (productId) => items.find((item) => item.product_id === productId)?.quantity ?? 0,
      busy,
      changeError,
      addOne,
      setQuantity,
      remove,
      reload,
    };
  }, [products, cart, busy, changeError, addOne, setQuantity, remove, reload]);

  return <CartContext.Provider value={value}>{children}</CartContext.Provider>;
}

export function useCart(): CartContextValue {
  const cart = useContext(CartContext);
  if (!cart) throw new Error('useCart needs a CartProvider.');
  return cart;
}

/** Plain-language availability for a product. */
export function stockLabel(stock: number): string {
  if (stock === 0) return 'Sold out';
  if (stock <= 5) return `Only ${stock} left`;
  return `${stock} in stock`;
}
