import '@fontsource-variable/archivo/wdth.css';
import './styles.css';

import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router';

import { GuestSessionProvider } from './api';
import { App } from './App';
import { CartProvider } from './features/cart/CartProvider';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <GuestSessionProvider>
        <CartProvider>
          <App />
        </CartProvider>
      </GuestSessionProvider>
    </BrowserRouter>
  </StrictMode>,
);
