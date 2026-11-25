import { afterEach, describe, expect, it, vi } from 'vitest';
import { createApiClient, createSessionStore } from './index';

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}
function capabilities(application = 'chat') {
  return {
    subject_id: '12345678-1234-4321-8123-123456789abc',
    application,
    policy_version: 'p1',
    roles: [],
    permission_codes: ['kb.read'],
  };
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
  it.each([401, 403, 503])(
    'removes protected content after a capability %s and can recover',
    async (status) => {
      let permissionStatus = 200;
      const fetcher = vi.fn<typeof fetch>().mockImplementation(async (url) => {
        const path = new URL(String(url)).pathname;
        if (path.includes('/authorization/'))
          return json(capabilities(), permissionStatus);
        if (path.endsWith('/config')) return json({ mode: 'local' });
        return json(session());
      });
      const store = createSessionStore(
        createApiClient('https://api.example/', fetcher),
        'chat',
      );
      await store.restore();
      expect(store.getSnapshot().state.status).toBe('authenticated');
      permissionStatus = status;
      await store.restore(true);
      expect(store.getSnapshot().state.status).toBe(
        status === 401 ? 'anonymous' : status === 403 ? 'forbidden' : 'error',
      );
      expect(store.getSnapshot().state).not.toHaveProperty('authorization');
      permissionStatus = 200;
      await store.restore();
      expect(store.getSnapshot().state.status).toBe('authenticated');
      store.stop();
    },
  );

  it('waits for permissions and ignores a late response after stop', async () => {
    let finish: ((response: Response) => void) | undefined;
    const fetcher = vi.fn<typeof fetch>().mockImplementation(async (url) => {
      const path = new URL(String(url)).pathname;
      if (path.includes('/authorization/'))
        return new Promise((resolve) => {
          finish = resolve;
        });
      return json(path.endsWith('/config') ? { mode: 'local' } : session());
    });
    const store = createSessionStore(
      createApiClient('https://api.example/', fetcher),
      'chat',
    );
    const pending = store.restore();
    await vi.waitFor(() => expect(finish).toBeDefined());
    expect(store.getSnapshot().state.status).toBe('checking');
    store.stop();
    finish?.(json(capabilities()));
    await pending;
    expect(store.getSnapshot().state.status).toBe('checking');
  });

  it('rechecks permissions each minute and drops visible content at cookie expiry during a slow check', async () => {
    vi.useFakeTimers();
    const original = {
      ...session(),
      expires_at: new Date(Date.now() + 120000).toISOString(),
    };
    let permissions = capabilities();
    let stalled = false;
    const fetcher = vi.fn<typeof fetch>().mockImplementation(async (url) => {
      const path = new URL(String(url)).pathname;
      if (stalled) return new Promise<Response>(() => {});
      if (path.includes('/authorization/')) return json(permissions);
      return json(path.endsWith('/config') ? { mode: 'local' } : original);
    });
    const store = createSessionStore(
      createApiClient('https://api.example/', fetcher),
      'chat',
    );
    await store.restore();
    permissions = {
      ...permissions,
      policy_version: 'p2',
      permission_codes: [],
    };
    await vi.advanceTimersByTimeAsync(60001);
    expect(store.getSnapshot().state).toMatchObject({
      authorization: { policyVersion: 'p2', permissionCodes: [] },
    });
    stalled = true;
    await vi.advanceTimersByTimeAsync(60000);
    expect(store.getSnapshot().state.status).toBe('checking');
    store.stop();
  });

  it('keeps an unavailable source anonymous without trying credentials', async () => {
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValue(json({ mode: 'unavailable' }));
    const store = createSessionStore(
      createApiClient('https://api.example/backend/', fetcher),
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
      .mockResolvedValueOnce(json(capabilities()))
      .mockResolvedValueOnce(new Response(null, { status: 204 }));
    const store = createSessionStore(
      createApiClient('https://api.example/backend/', fetcher),
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
    expect(fetcher.mock.calls[3]?.[1]).toMatchObject({
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
      .mockResolvedValueOnce(json(session()))
      .mockResolvedValueOnce(json(capabilities()));
    const store = createSessionStore(
      createApiClient('https://api.example/', fetcher),
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
      '/api/v1/authorization/chat/me',
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
      if (path.includes('/authorization/')) return json(capabilities());
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
      createApiClient('https://api.example/', fetcher),
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
      if (path.includes('/authorization/')) return json(capabilities());
      if (path.endsWith('/config')) return json({ mode: 'local' });
      if (path.endsWith('/me')) return json(active);
      if (path.endsWith('/refresh')) {
        refreshes += 1;
        active = session();
        return json(active);
      }
      throw new Error('Unexpected authentication call');
    });
    const client = createApiClient('https://api.example/', fetcher);
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
      .mockResolvedValueOnce(json(capabilities()))
      .mockResolvedValueOnce(json({ mode: 'local' }))
      .mockResolvedValueOnce(json(session()))
      .mockResolvedValueOnce(json(capabilities()));
    const store = createSessionStore(
      createApiClient('https://api.example/', fetcher),
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
      if (path.includes('/authorization/')) return json(capabilities());
      if (path.endsWith('/config')) return json({ mode: 'local' });
      if (path.endsWith('/me')) return json(original);
      if (path.endsWith('/refresh')) {
        refreshes += 1;
        throw new TypeError('response was lost');
      }
      throw new Error('Unexpected authentication call');
    });
    const client = createApiClient('https://api.example/', fetcher);
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
      createApiClient('https://api.example/', fetcher),
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
      createApiClient('https://api.example/', fetcher),
      'chat',
      async (operation) => operation(),
    );
    await expect(
      store.login(
        { username: 'test', password: 'transient-password' },
        new AbortController().signal,
      ),
    ).rejects.toThrow('Invalid session response');
    expect(store.getSnapshot().state.status).toBe('error');
    store.stop();
  });
});
