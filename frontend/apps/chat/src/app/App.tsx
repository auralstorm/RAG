import { RouterProvider } from 'react-router';
import type { DataRouter } from 'react-router';
import { UNCONNECTED_SESSION } from '@enterprise-rag/shared';
import type { SessionState, SessionActions } from '@enterprise-rag/shared';
import { SessionProvider } from '@enterprise-rag/ui';
import { AppProviders } from './AppProviders';

export function App({
  router,
  session = UNCONNECTED_SESSION,
  actions,
}: {
  readonly router: DataRouter;
  readonly session?: SessionState;
  readonly actions?: SessionActions;
}) {
  return (
    <AppProviders>
      <SessionProvider state={session} actions={actions}>
        <RouterProvider router={router} />
      </SessionProvider>
    </AppProviders>
  );
}
