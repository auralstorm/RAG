import type { DataRouter } from 'react-router';

// Await lazy route initialization/redirects, rather than timing their module imports.
export function waitForRouter(
  router: DataRouter,
  ready: (state: DataRouter['state']) => boolean = (state) => state.initialized,
): Promise<void> {
  if (ready(router.state)) return Promise.resolve();
  return new Promise((resolve) => {
    const unsubscribe = router.subscribe((state) => {
      if (ready(state)) {
        unsubscribe();
        resolve();
      }
    });
  });
}
