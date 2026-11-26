import { fileURLToPath, URL } from 'node:url';

import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

import pkg from './package.json' with { type: 'json' };
import { proMockPlugin } from './vite-plugins/mockPlugin';

// https://vite.dev/config/
export default defineConfig(() => ({
  plugins: [react(), tailwindcss(), proMockPlugin()],
  define: {
    __APP_VERSION__: JSON.stringify(pkg.version),
    __REACT_VERSION__: JSON.stringify(
      (pkg.dependencies?.react || '').replace(/^[\^~]/, ''),
    ),
    __VITE_VERSION__: JSON.stringify('8.3.6'),
    'process.env.COMMIT_HASH': JSON.stringify(process.env.COMMIT_HASH || ''),
  },
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
      '@root': fileURLToPath(new URL('.', import.meta.url)),
    },
  },
  css: {
    preprocessorOptions: {
      less: {
        javascriptEnabled: true,
      },
    },
  },
  server: {
    host: '127.0.0.1',
    port: 5174,
    strictPort: true,
    proxy: {
      '/backend': {
        target: 'http://127.0.0.1:8000',
        rewrite: (path) => path.replace(/^\/backend(?=\/|$)/, ''),
      },
    },
  },
}));
