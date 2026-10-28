import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

// Same rule as the API's CLOUDCART_RELEASE_VERSION, so both footers show comparable identifiers.
const RELEASE_PATTERN = /^[A-Za-z0-9][A-Za-z0-9.+_-]{0,63}$/;
const release = process.env.CLOUDCART_RELEASE_VERSION ?? 'dev';
if (!RELEASE_PATTERN.test(release)) {
  throw new Error('CLOUDCART_RELEASE_VERSION must match ' + RELEASE_PATTERN.source);
}

// The dev and preview servers forward /api to a local API. changeOrigin stays false so the
// browser's Host header reaches the API: its same-origin check refuses state changes otherwise.
const apiProxy = {
  '/api': { target: process.env.CLOUDCART_API_URL ?? 'http://127.0.0.1:8000', changeOrigin: false },
};

export default defineConfig({
  plugins: [react()],
  define: { __STOREFRONT_VERSION__: JSON.stringify(release) },
  server: { proxy: apiProxy },
  preview: { proxy: apiProxy },
});
