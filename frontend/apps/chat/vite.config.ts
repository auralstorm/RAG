import { fileURLToPath } from 'node:url';

import react from '@vitejs/plugin-react';
import { defineConfig, loadEnv } from 'vite';

// https://vite.dev/config/
export default defineConfig(({ mode }) => ({
  plugins: [react()],
  resolve: {
    alias: {
      '@chat': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    proxy: {
      '/backend': {
        target:
          loadEnv(mode, process.cwd(), '').API_PROXY_TARGET ||
          'http://127.0.0.1:8000',
        rewrite: (path) => path.replace(/^\/backend(?=\/|$)/, ''),
      },
    },
  },
}));
