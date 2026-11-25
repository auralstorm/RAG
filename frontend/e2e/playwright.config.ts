import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: '.',
  testMatch: '*.spec.ts',
  outputDir: '../../.poc-results/frontend/admin-pro',
  workers: 1,
  retries: 0,
  timeout: 120_000,
  expect: { timeout: 10_000 },
  reporter: 'list',
  use: {
    browserName: 'chromium',
    headless: true,
    ...(process.env['ENTERPRISE_RAG_BROWSER_EXECUTABLE']
      ? {
          launchOptions: {
            executablePath: process.env['ENTERPRISE_RAG_BROWSER_EXECUTABLE'],
          },
        }
      : {}),
  },
});
