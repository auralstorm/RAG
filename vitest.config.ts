import react from '@vitejs/plugin-react';
import { defineConfig } from 'vitest/config';

export default defineConfig({
  plugins: [react()],
  test: {
    include: ['frontend/**/*.test.{ts,tsx}'],
    environment: 'jsdom',
    setupFiles: ['./frontend/tests/setup.ts'],
    restoreMocks: true,
  },
});
