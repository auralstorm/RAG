import js from '@eslint/js';
import globals from 'globals';
import reactHooks from 'eslint-plugin-react-hooks';
import reactRefresh from 'eslint-plugin-react-refresh';
import tseslint from 'typescript-eslint';
import { defineConfig, globalIgnores } from 'eslint/config';

const forbidImports = (patterns) => [
  'error',
  {
    patterns: [
      {
        group: patterns,
        message: 'Use the owning workspace package and its public exports.',
      },
    ],
  },
];

export default defineConfig([
  globalIgnores(['**/dist/**', '**/node_modules/**']),
  {
    files: ['**/*.{js,mjs}'],
    extends: [js.configs.recommended],
    languageOptions: { globals: globals.node },
  },
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      js.configs.recommended,
      tseslint.configs.recommended,
      reactHooks.configs.flat.recommended,
    ],
    languageOptions: { globals: { ...globals.browser, ...globals.node } },
  },
  {
    files: ['frontend/apps/*/src/**/*.{ts,tsx}'],
    extends: [reactRefresh.configs.vite],
  },
  {
    files: ['frontend/apps/chat/**/*.{ts,tsx}'],
    rules: {
      'no-restricted-imports': forbidImports([
        '@enterprise-rag/admin',
        '**/apps/admin/**',
        '**/admin/src/**',
        '**/packages/*/src/**',
      ]),
    },
  },
  {
    files: ['frontend/apps/admin/**/*.{ts,tsx}'],
    rules: {
      'no-restricted-imports': forbidImports([
        '@enterprise-rag/chat',
        '**/apps/chat/**',
        '**/chat/src/**',
        '**/packages/*/src/**',
      ]),
    },
  },
  {
    files: ['frontend/packages/**/*.{ts,tsx}'],
    rules: {
      'no-restricted-imports': forbidImports([
        '@enterprise-rag/chat',
        '@enterprise-rag/admin',
        '**/apps/**',
      ]),
    },
  },
]);
