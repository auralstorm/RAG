import type { SessionCredentials, SessionState } from '@enterprise-rag/shared';
import { HttpError } from './index';
import type { AuthSessionResponse, createApiClient } from './index';

type SessionClient = Pick<
  ReturnType<typeof createApiClient>,
  'auth' | 'authorization'
>;
type SessionCoordinator = <T>(
  operation: () => Promise<T>,
  signal: AbortSignal,
) => Promise<T>;
interface Snapshot {
  readonly state: SessionState;
  readonly mode: 'local' | 'unavailable';
}

export function createSessionStore(
  api: SessionClient,
  application: 'chat' | 'admin',
  coordinator?: SessionCoordinator,
) {
  const client = api.auth;
  const browserLocks =
    typeof navigator !== 'undefined' ? navigator.locks : undefined;
  const markerKey = `enterprise-rag-auth-mutation:${application}`;
  const sharedStorage = (() => {
    try {
      return typeof localStorage !== 'undefined' ? localStorage : undefined;
    } catch {
      return undefined;
    }
  })();
  const canRenew = Boolean((coordinator || browserLocks) && sharedStorage);
  const coordinate: SessionCoordinator =
    coordinator ??
    ((operation, signal) =>
      browserLocks
        ? browserLocks.request(
            `enterprise-rag-session:${application}`,
            { signal },
            operation,
          )
        : operation());
  let snapshot: Snapshot = {
    state: { status: 'checking' },
    mode: 'unavailable',
  };
  let request: AbortController | null = null;
  let pending: Promise<void> | null = null;
  let generation = 0;
  let renewal: ReturnType<typeof setTimeout> | undefined;
  let expiration: ReturnType<typeof setTimeout> | undefined;
  let csrf = '';
  let hadSession = false;
  let mutating = false;
  let uncertainRefresh = false;
  let logoutRequested = false;
  const listeners = new Set<() => void>();

  function marker():
    { kind: 'refresh' | 'logout'; previousExpiry: string | null } | undefined {
    const raw = sharedStorage?.getItem(markerKey);
    if (!raw) return undefined;
    const value: unknown = JSON.parse(raw);
    if (
      typeof value !== 'object' ||
      value === null ||
      !('kind' in value) ||
      !('previousExpiry' in value) ||
      (value.kind !== 'refresh' && value.kind !== 'logout') ||
      (value.previousExpiry !== null &&
        typeof value.previousExpiry !== 'string')
    )
      throw new Error('Authentication result requires confirmation');
    return { kind: value.kind, previousExpiry: value.previousExpiry };
  }
  function mark(kind: 'refresh' | 'logout', previousExpiry: string | null) {
    if (!sharedStorage)
      throw new Error('Safe session coordination is unavailable');
    // This denial-only marker contains no credentials or user identity. It survives
    // a tab crash or lost response, so a second tab cannot replay an uncertain write.
    sharedStorage.setItem(markerKey, JSON.stringify({ kind, previousExpiry }));
  }
  function clearMarker() {
    sharedStorage?.removeItem(markerKey);
  }

  function publish(state: SessionState, mode = snapshot.mode) {
    snapshot = { state, mode };
    for (const listener of listeners) listener();
  }
  function stop() {
    generation += 1;
    // An in-flight cookie mutation must finish receiving its response. Aborting a
    // request cannot undo server rotation or logout, and must not start a replay.
    if (!mutating) request?.abort();
    request = null;
    pending = null;
    clearTimeout(renewal);
    clearTimeout(expiration);
    csrf = '';
    publish({ status: 'checking' });
  }
  function failure(error: unknown) {
    csrf = '';
    clearTimeout(renewal);
    clearTimeout(expiration);
    if (error instanceof HttpError && error.status === 401)
      publish(
        hadSession
          ? { status: 'anonymous', reason: 'expired' }
          : { status: 'anonymous' },
      );
    else if (error instanceof HttpError && error.status === 403)
      publish({ status: 'forbidden' });
    else
      publish(
        error instanceof HttpError && error.requestId
          ? { status: 'error', requestId: error.requestId }
          : { status: 'error' },
      );
  }
  async function authenticated(
    response: AuthSessionResponse,
    signal: AbortSignal,
    revision: number,
  ) {
    const capabilities = await api.authorization.capabilities(
      application,
      response.user.id,
      signal,
    );
    if (signal.aborted || revision !== generation) return;
    if (Date.parse(response.expires_at) <= Date.now()) throw new HttpError(401);
    hadSession = true;
    csrf = response.csrf_token;
    clearTimeout(expiration);
    expiration = setTimeout(
      () => {
        // A slow background check cannot extend the life of visible protected data.
        publish({ status: 'checking' });
      },
      Math.max(0, Date.parse(response.expires_at) - Date.now()),
    );
    publish(
      {
        status: 'authenticated',
        subjectId: response.user.id,
        canAccessApplication: true,
        authorization: {
          policyVersion: capabilities.policy_version,
          permissionCodes: capabilities.permission_codes,
        },
      },
      'local',
    );
    clearTimeout(renewal);
    renewal = setTimeout(
      () => {
        void restore(true, true);
      },
      Math.min(
        60_000,
        Math.max(
          1000,
          Date.parse(response.expires_at) -
            Date.now() -
            (canRenew && !uncertainRefresh ? 30_000 : 0),
        ),
      ),
    );
  }
  function perform(
    work: (signal: AbortSignal, revision: number) => Promise<void>,
  ): Promise<void> {
    const controller = new AbortController();
    request = controller;
    const revision = generation;
    const running = work(controller.signal, revision).finally(() => {
      if (pending === running) {
        pending = null;
        request = null;
      }
    });
    pending = running;
    return running;
  }
  async function readSession(
    signal: AbortSignal,
    renewSoon: boolean,
  ): Promise<AuthSessionResponse> {
    const shared = marker();
    if (shared?.kind === 'logout') throw new HttpError(401);
    uncertainRefresh = Boolean(shared);
    let current: AuthSessionResponse | undefined;
    try {
      current = await client.me(application, signal);
    } catch (error) {
      if (!(error instanceof HttpError) || error.status !== 401) throw error;
      if (!canRenew || uncertainRefresh) throw error;
    }
    if (
      shared?.kind === 'refresh' &&
      current &&
      shared.previousExpiry &&
      Date.parse(current.expires_at) > Date.parse(shared.previousExpiry)
    ) {
      // A newer server-verified access cookie proves another tab received rotation.
      clearMarker();
      uncertainRefresh = false;
    }
    if (
      current &&
      (uncertainRefresh ||
        !renewSoon ||
        Date.parse(current.expires_at) - Date.now() > 30_000 ||
        !canRenew)
    )
      return current;
    const token =
      current?.csrf_token ?? (await client.csrf(application, signal));
    mark('refresh', current?.expires_at ?? null);
    mutating = true;
    uncertainRefresh = true;
    try {
      const response = await client.refresh(application, token, signal);
      clearMarker();
      uncertainRefresh = false;
      return response;
    } finally {
      mutating = false;
    }
  }
  function restore(background = false, renewSoon = false): Promise<void> {
    // Focus and timers share an operation; they cannot cancel or replay writes.
    if (pending) return pending;
    if (logoutRequested) return Promise.resolve();
    if (!background) publish({ status: 'checking' });
    clearTimeout(renewal);
    return perform(async (signal, revision) => {
      try {
        const response = await coordinate(async () => {
          const config = await client.configuration(application, signal);
          if (signal.aborted || revision !== generation) return undefined;
          if (config.mode === 'unavailable') {
            clearTimeout(expiration);
            csrf = '';
            hadSession = false;
            publish({ status: 'anonymous' }, 'unavailable');
            return undefined;
          }
          if (!background) publish({ status: 'checking' }, 'local');
          else if (snapshot.mode !== 'local') publish(snapshot.state, 'local');
          // The lock owner re-reads cookies through /me: another tab may already
          // have rotated. Only an expired/near-expiry credential is refreshed.
          return readSession(signal, renewSoon);
        }, signal);
        if (response && !signal.aborted && revision === generation)
          await authenticated(response, signal, revision);
      } catch (error) {
        if (!signal.aborted && revision === generation) failure(error);
      }
    });
  }
  async function login(credentials: SessionCredentials, signal: AbortSignal) {
    if (pending) await pending;
    if (signal.aborted) return;
    clearTimeout(renewal);
    return perform(async (_signal, revision) => {
      try {
        const response = await coordinate(
          () => client.login(application, credentials, signal),
          signal,
        );
        if (!signal.aborted && revision === generation) {
          uncertainRefresh = false;
          logoutRequested = false;
          clearMarker();
          await authenticated(response, signal, revision);
        }
      } catch (error) {
        if (!signal.aborted && revision === generation) failure(error);
        throw error;
      }
    });
  }
  async function logout() {
    if (pending) await pending;
    clearTimeout(renewal);
    clearTimeout(expiration);
    logoutRequested = true;
    publish({ status: 'checking' });
    return perform(async (signal, revision) => {
      try {
        await coordinate(async () => {
          const token = csrf || (await client.csrf(application, signal));
          mark('logout', null);
          mutating = true;
          try {
            await client.logout(application, token, signal);
            clearMarker();
          } finally {
            mutating = false;
          }
        }, signal);
        if (!signal.aborted && revision === generation) {
          csrf = '';
          hadSession = false;
          logoutRequested = false;
          publish({ status: 'anonymous' });
        }
      } catch (error) {
        if (!signal.aborted && revision === generation) failure(error);
      }
    });
  }
  return {
    getSnapshot: () => snapshot,
    subscribe(listener: () => void) {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
    start() {
      void restore();
      return stop;
    },
    restore,
    login,
    logout,
    stop,
  };
}
