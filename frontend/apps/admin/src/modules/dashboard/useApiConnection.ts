import { useEffect, useRef, useState } from 'react';
import { HttpError } from '@enterprise-rag/api-client';
import { apiClient } from '@admin/api/apiClient';

type ConnectionState =
  | { readonly status: 'idle' | 'loading' | 'connected' }
  | { readonly status: 'error'; readonly requestId: string | undefined };

export function useApiConnection() {
  const [state, setState] = useState<ConnectionState>({ status: 'idle' });
  const request = useRef<AbortController | null>(null);
  useEffect(
    () => () => {
      request.current?.abort();
      request.current = null;
    },
    [],
  );

  async function checkConnection() {
    if (request.current) return;
    const controller = new AbortController();
    request.current = controller;
    setState({ status: 'loading' });
    try {
      await apiClient.getLiveness(
        AbortSignal.any([controller.signal, AbortSignal.timeout(10_000)]),
      );
      if (!controller.signal.aborted) setState({ status: 'connected' });
    } catch (error) {
      if (!controller.signal.aborted) {
        setState({
          status: 'error',
          requestId: error instanceof HttpError ? error.requestId : undefined,
        });
      }
    } finally {
      if (request.current === controller) request.current = null;
    }
  }

  return { state, checkConnection };
}
