import { useEffect, useSyncExternalStore } from 'react';
import type { DataRouter } from 'react-router';

import { apiClient } from '@chat/api/apiClient';
import { createSessionStore } from '@enterprise-rag/api-client';

import { App } from './App';

const sessionStore = createSessionStore(apiClient, 'chat');

export function ConnectedApp({ router }: { readonly router: DataRouter }) {
  const snapshot = useSyncExternalStore(
    sessionStore.subscribe,
    sessionStore.getSnapshot,
  );
  useEffect(() => {
    const stop = sessionStore.start();
    const restore = () => {
      void sessionStore.restore(true);
    };
    window.addEventListener('focus', restore);
    return () => {
      window.removeEventListener('focus', restore);
      stop();
    };
  }, []);
  return (
    <App
      router={router}
      session={snapshot.state}
      actions={{
        mode: snapshot.mode,
        ...(snapshot.mode === 'local'
          ? { login: sessionStore.login, logout: sessionStore.logout }
          : {}),
      }}
    />
  );
}
