import { RouterProvider } from 'react-router';
import type { DataRouter } from 'react-router';
import { UNCONNECTED_SESSION } from '@enterprise-rag/shared';
import type { SessionState } from '@enterprise-rag/shared';
import { SessionProvider } from '@enterprise-rag/ui';
import { AppProviders } from './AppProviders';

export function App({
  router,
  session = UNCONNECTED_SESSION,
}: {
  readonly router: DataRouter;
  readonly session?: SessionState;
}) {
  return (
    <AppProviders>
      <SessionProvider state={session}>
        <RouterProvider router={router} />
      </SessionProvider>
    </AppProviders>
  );
}
