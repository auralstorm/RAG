import { afterEach, describe, expect, it, vi } from 'vitest';
import { loadReplySource } from './load-reply-source';

afterEach(() => vi.unstubAllEnvs());

describe('reply source initialization', () => {
  it('loads the mock source in development', async () => {
    vi.stubEnv('DEV', true);
    vi.stubEnv('MODE', 'development');
    const source = await loadReplySource();
    expect(source?.notice).toBe('开发环境 · 回答为模拟内容');
  });

  it.each(['production', 'test', 'staging'])(
    'does not load mocks in %s mode',
    async (mode) => {
      vi.stubEnv('MODE', mode);
      vi.stubEnv('DEV', mode === 'test');
      expect(await loadReplySource()).toBeNull();
    },
  );

  it('does not enable mocks in a production build named development', async () => {
    vi.stubEnv('MODE', 'development');
    vi.stubEnv('DEV', false);
    expect(await loadReplySource()).toBeNull();
  });
});
it('never loads developer answers for a protected workspace', async () => {
  vi.stubEnv('DEV', true);
  vi.stubEnv('MODE', 'development');
  expect(await loadReplySource(false)).toBeNull();
});
