import react from '@vitejs/plugin-react';
import { defineConfig } from 'vitest/config';
import { fileURLToPath } from 'node:url';

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@admin': fileURLToPath(
        new URL('./frontend/apps/admin/src', import.meta.url),
      ),
      '@chat': fileURLToPath(
        new URL('./frontend/apps/chat/src', import.meta.url),
      ),
    },
  },
  test: {
    include: ['frontend/**/*.test.{ts,tsx}'],
    environment: 'jsdom',
    // Large component libraries make one worker per CPU expensive on CI runners.
    maxWorkers: 2,
    setupFiles: ['./frontend/tests/setup.ts'],
    restoreMocks: true,
  },
});
