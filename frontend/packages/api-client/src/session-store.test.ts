import { afterEach, describe, expect, it, vi } from 'vitest';
import { createApiClient, createSessionStore } from './index';

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}
function session(application = 'chat') {
  return {
    application,
    csrf_token: 'a'.repeat(64),
    expires_at: new Date(Date.now() + 60000).toISOString(),
    user: {
      id: '12345678-1234-4321-8123-123456789abc',
      schema_version: '1.0',
      display_name: '测试用户',
      status: 'ACTIVE',
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
    },
  };
}
afterEach(() => {
  vi.useRealTimers();
  localStorage.clear();
});

describe('trusted cookie session lifecycle', () => {
  it('keeps an unavailable source anonymous without trying credentials', async () => {
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValue(json({ mode: 'unavailable' }));
    const store = createSessionStore(
      createApiClient('https://api.example/backend/', fetcher).auth,
      'chat',
      async (operation) => operation(),
    );
    await store.restore();
    expect(store.getSnapshot()).toEqual({
      state: { status: 'anonymous' },
      mode: 'unavailable',
    });
    expect(fetcher).toHaveBeenCalledTimes(1);
    store.stop();
  });
  it('restores from the server and logs out without persisting a token', async () => {
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(json({ mode: 'local' }))
      .mockResolvedValueOnce(json(session()))
      .mockResolvedValueOnce(new Response(null, { status: 204 }));
    const store = createSessionStore(
      createApiClient('https://api.example/backend/', fetcher).auth,
      'chat',
      async (operation) => operation(),
    );
    await store.restore();
    expect(store.getSnapshot().state).toMatchObject({
      status: 'authenticated',
      subjectId: session().user.id,
    });
    await store.logout();
    expect(store.getSnapshot().state.status).toBe('anonymous');
    expect(fetcher.mock.calls[2]?.[1]).toMatchObject({
      method: 'POST',
      credentials: 'include',
      headers: { 'X-CSRF-Token': 'a'.repeat(64) },
    });
    store.stop();
  });
  it('recovers CSRF after an expired access cookie and rotates refresh only once', async () => {
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(json({ mode: 'local' }))
      .mockResolvedValueOnce(json({}, 401))
      .mockResolvedValueOnce(json({ csrf_token: 'b'.repeat(64) }))
      .mockResolvedValueOnce(json(session()));
    const store = createSessionStore(
      createApiClient('https://api.example/', fetcher).auth,
      'chat',
      async (operation) => operation(),
    );
    await store.restore();
    expect(store.getSnapshot().state.status).toBe('authenticated');
    expect(
      fetcher.mock.calls.map((call) => new URL(String(call[0])).pathname),
    ).toEqual([
      '/api/v1/auth/chat/config',
      '/api/v1/auth/chat/me',
      '/api/v1/auth/chat/csrf',
      '/api/v1/auth/chat/refresh',
    ]);
    expect(fetcher.mock.calls[3]?.[1]).toMatchObject({
      method: 'POST',
      headers: { 'X-CSRF-Token': 'b'.repeat(64) },
    });
    store.stop();
  });
  it('does not replay a renewal after an uncertain server mutation', async () => {
    vi.useFakeTimers();
    const original = session();
    let refreshes = 0;
    const fetcher = vi.fn<typeof fetch>().mockImplementation(async (url) => {
      const path = new URL(String(url)).pathname;
      if (path.endsWith('/config')) return json({ mode: 'local' });
      if (path.endsWith('/me'))
        return refreshes ? json({}, 401) : json(original);
      if (path.endsWith('/refresh')) {
        refreshes += 1;
        return json({}, 503);
      }
      throw new Error('Unexpected authentication call');
    });
    const store = createSessionStore(
      createApiClient('https://api.example/', fetcher).auth,
      'chat',
      async (operation) => operation(),
    );
    await store.restore();
    await vi.advanceTimersByTimeAsync(30001);
    expect(store.getSnapshot().state.status).toBe('error');
    await store.restore(true);
    expect(store.getSnapshot().state.status).toBe('anonymous');
    expect(refreshes).toBe(1);
    store.stop();
  });

  it('serializes two tabs and rechecks the cookie session before rotating', async () => {
    vi.useFakeTimers();
    let active = session();
    let refreshes = 0;
    let tail = Promise.resolve();
    function coordinate<T>(operation: () => Promise<T>): Promise<T> {
      const next = tail.then(operation);
      tail = next.then(
        () => undefined,
        () => undefined,
      );
      return next;
    }
    const fetcher = vi.fn<typeof fetch>().mockImplementation(async (url) => {
      const path = new URL(String(url)).pathname;
      if (path.endsWith('/config')) return json({ mode: 'local' });
      if (path.endsWith('/me')) return json(active);
      if (path.endsWith('/refresh')) {
        refreshes += 1;
        active = session();
        return json(active);
      }
      throw new Error('Unexpected authentication call');
    });
    const client = createApiClient('https://api.example/', fetcher).auth;
    const first = createSessionStore(client, 'chat', coordinate);
    const second = createSessionStore(client, 'chat', coordinate);
    await Promise.all([first.restore(), second.restore()]);
    await vi.advanceTimersByTimeAsync(30001);
    expect(refreshes).toBe(1);
    expect(first.getSnapshot().state.status).toBe('authenticated');
    expect(second.getSnapshot().state.status).toBe('authenticated');
    first.stop();
    second.stop();
  });

  it('keeps authenticated content during background revalidation', async () => {
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(json({ mode: 'local' }))
      .mockResolvedValueOnce(json(session()))
      .mockResolvedValueOnce(json({ mode: 'local' }))
      .mockResolvedValueOnce(json(session()));
    const store = createSessionStore(
      createApiClient('https://api.example/', fetcher).auth,
      'chat',
      async (operation) => operation(),
    );
    await store.restore();
    const states: string[] = [];
    store.subscribe(() => states.push(store.getSnapshot().state.status));
    await store.restore(true);
    expect(states).not.toContain('checking');
    store.stop();
  });

  it('shares an uncertain renewal marker so another tab cannot replay it', async () => {
    vi.useFakeTimers();
    const original = session();
    let refreshes = 0;
    let tail = Promise.resolve();
    function coordinate<T>(operation: () => Promise<T>): Promise<T> {
      const next = tail.then(operation);
      tail = next.then(
        () => undefined,
        () => undefined,
      );
      return next;
    }
    const fetcher = vi.fn<typeof fetch>().mockImplementation(async (url) => {
      const path = new URL(String(url)).pathname;
      if (path.endsWith('/config')) return json({ mode: 'local' });
      if (path.endsWith('/me')) return json(original);
      if (path.endsWith('/refresh')) {
        refreshes += 1;
        throw new TypeError('response was lost');
      }
      throw new Error('Unexpected authentication call');
    });
    const client = createApiClient('https://api.example/', fetcher).auth;
    const first = createSessionStore(client, 'chat', coordinate);
    const second = createSessionStore(client, 'chat', coordinate);
    await Promise.all([first.restore(), second.restore()]);
    await vi.advanceTimersByTimeAsync(30001);
    expect(refreshes).toBe(1);
    await second.restore(true, true);
    expect(refreshes).toBe(1);
    expect(localStorage.getItem('enterprise-rag-auth-mutation:chat')).toContain(
      'refresh',
    );
    first.stop();
    second.stop();
  });
  it('drops a late login response after cancellation', async () => {
    let finish: ((response: Response) => void) | undefined;
    const fetcher = vi.fn<typeof fetch>().mockImplementation(
      () =>
        new Promise((resolve) => {
          finish = resolve;
        }),
    );
    const store = createSessionStore(
      createApiClient('https://api.example/', fetcher).auth,
      'chat',
      async (operation) => operation(),
    );
    const controller = new AbortController();
    const pending = store.login(
      { username: 'test', password: 'transient-password' },
      controller.signal,
    );
    controller.abort();
    finish?.(json(session()));
    await pending;
    expect(store.getSnapshot().state.status).toBe('checking');
    store.stop();
  });
  it('rejects a different application response', async () => {
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(json(session('admin')));
    const store = createSessionStore(
      createApiClient('https://api.example/', fetcher).auth,
      'chat',
      async (operation) => operation(),
    );
    await expect(
      store.login(
        { username: 'test', password: 'transient-password' },
        new AbortController().signal,
      ),
    ).rejects.toThrow('Invalid session response');
    expect(store.getSnapshot().state.status).toBe('checking');
    store.stop();
  });
});
