import { defineConfig, devices } from '@playwright/test';

import {
  ADMIN_PASSWORD,
  API_PORT,
  API_RELEASE,
  STOREFRONT_RELEASE,
  WEB_PORT,
  requireTestDependencies,
  shellCommand,
  stackCommand,
} from './tests/support/stack';

requireTestDependencies();

// One browser test at a time: tests share one API, one worker, and one product catalog.
export default defineConfig({
  testDir: './tests',
  fullyParallel: false,
  workers: 1,
  forbidOnly: !!process.env.CI,
  retries: 0,
  timeout: 60_000,
  expect: { timeout: 10_000 },
  reporter: [['list']],
  use: {
    baseURL: `http://localhost:${WEB_PORT}`,
    trace: 'retain-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: [
    {
      command: shellCommand(stackCommand('serve-api', '--port', String(API_PORT), '--release', API_RELEASE)),
      url: `http://127.0.0.1:${API_PORT}/api/v1/version`,
      env: { CLOUDCART_E2E_ADMIN_PASSWORD: ADMIN_PASSWORD },
      timeout: 120_000,
      reuseExistingServer: false,
      gracefulShutdown: { signal: 'SIGTERM', timeout: 5_000 },
      stdout: 'pipe',
    },
    {
      // A production build behind `vite preview`, which forwards /api to the API with the original Host.
      command: `npm run build && npm run preview -- --host localhost --port ${WEB_PORT} --strictPort`,
      url: `http://localhost:${WEB_PORT}/`,
      env: { CLOUDCART_RELEASE_VERSION: STOREFRONT_RELEASE, CLOUDCART_API_URL: `http://127.0.0.1:${API_PORT}` },
      timeout: 120_000,
      reuseExistingServer: false,
    },
  ],
});
