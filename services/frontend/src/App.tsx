import { useEffect, useState, type MouseEvent } from 'react';
import { Link, NavLink, Route, Routes } from 'react-router';

import { api, call, useGuestSession } from './api';
import { AdminPage } from './features/admin/AdminPage';
import { CartPage } from './features/cart/CartPage';
import { useCart } from './features/cart/CartProvider';
import { CatalogPage } from './features/catalog/CatalogPage';
import { OrderPage } from './features/orders/OrderPage';
import { OrdersPage } from './features/orders/OrdersPage';
import { ReceiptPage } from './features/orders/ReceiptPage';
import { plural } from './format';

export function App() {
  function skipToContent(event: MouseEvent<HTMLAnchorElement>) {
    event.preventDefault();
    document.getElementById('main')?.focus();
  }

  return (
    <>
      <a className="skip-link" href="#main" onClick={skipToContent}>
        Skip to content
      </a>
      <p className="practice-strip">This is a practice shop: payments are simulated and nothing is shipped.</p>
      <header className="site-header">
        <div className="wrap header-inner">
          <Link to="/" className="brand">
            CloudCart
          </Link>
          <nav aria-label="Main">
            <NavLink to="/" end>
              Shop
            </NavLink>
            <NavLink to="/orders">Orders</NavLink>
            <CartLink />
          </nav>
        </div>
      </header>
      <main id="main" tabIndex={-1} className="wrap">
        <SessionNotice />
        <CartChangeProblem />
        <Routes>
          <Route path="/" element={<CatalogPage />} />
          <Route path="/cart" element={<CartPage />} />
          <Route path="/orders" element={<OrdersPage />} />
          <Route path="/orders/:orderId" element={<OrderPage />} />
          <Route path="/orders/:orderId/receipt" element={<ReceiptPage />} />
          <Route path="/admin" element={<AdminPage />} />
          <Route path="*" element={<PageNotFound />} />
        </Routes>
      </main>
      <Footer />
    </>
  );
}

function CartLink() {
  const { count } = useCart();
  return (
    <NavLink to="/cart" className="cart-link" aria-label={`Cart, ${plural(count, 'item', 'items')}`}>
      Cart
      {count > 0 && (
        <span className="cart-count" aria-hidden="true">
          {count}
        </span>
      )}
    </NavLink>
  );
}

function SessionNotice() {
  const { sessionEnded, dismissSessionEnded } = useGuestSession();
  if (!sessionEnded) return null;
  return (
    <div className="notice" role="status">
      <p>Your previous session ended, so you have a new, empty cart. Earlier orders stay with the old session.</p>
      <button type="button" className="button link" onClick={dismissSessionEnded}>
        Dismiss
      </button>
    </div>
  );
}

function CartChangeProblem() {
  const { changeError } = useCart();
  if (!changeError) return null;
  return (
    <p className="problem" role="alert">
      Your cart was not changed. {changeError}
    </p>
  );
}

function Footer() {
  const [apiVersion, setApiVersion] = useState<string | null>(null);

  useEffect(() => {
    call(() => api.GET('/api/v1/version')).then(
      ({ version }) => setApiVersion(version),
      () => setApiVersion('unavailable'),
    );
  }, []);

  return (
    <footer className="site-footer">
      <div className="wrap footer-inner">
        <p className="versions">
          <span>Storefront {__STOREFRONT_VERSION__}</span>
          <span>API {apiVersion ?? 'checking'}</span>
        </p>
        <Link to="/admin">Instructor view</Link>
      </div>
    </footer>
  );
}

function PageNotFound() {
  return (
    <div className="page-intro">
      <h1>Page not found</h1>
      <p>
        <Link to="/">Go to the shop</Link>
      </p>
    </div>
  );
}
