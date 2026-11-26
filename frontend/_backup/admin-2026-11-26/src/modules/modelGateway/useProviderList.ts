import { useEffect, useState } from 'react';

import { apiClient } from '@admin/api/apiClient';
import { HttpError, type ProviderAdminView } from '@enterprise-rag/api-client';

export interface ProviderListQuery {
  readonly page: number;
  readonly page_size: number;
  readonly name?: string;
  readonly provider_type?: string;
  readonly status?: 'ACTIVE' | 'DISABLED';
}

type ProviderListState =
  | {
      readonly status: 'loading';
      readonly items: readonly ProviderAdminView[];
      readonly total: number;
    }
  | {
      readonly status: 'ready';
      readonly items: readonly ProviderAdminView[];
      readonly total: number;
    }
  | {
      readonly status: 'error';
      readonly items: readonly ProviderAdminView[];
      readonly total: number;
      readonly requestId?: string;
      readonly accessDenied?: 401 | 403;
    };

export function useProviderList(query: ProviderListQuery, refreshKey: number) {
  const { page, page_size, name, provider_type, status } = query;
  const key = JSON.stringify([
    page,
    page_size,
    name,
    provider_type,
    status,
    refreshKey,
  ]);
  const [snapshot, setSnapshot] = useState<{
    readonly key: string;
    readonly state: ProviderListState;
  }>();

  useEffect(() => {
    const controller = new AbortController();
    void apiClient.providers
      .list(
        {
          page,
          page_size,
          ...(name ? { name } : {}),
          ...(provider_type ? { provider_type } : {}),
          ...(status ? { status } : {}),
        },
        controller.signal,
      )
      .then((result) => {
        if (!controller.signal.aborted)
          setSnapshot({
            key,
            state: {
              status: 'ready',
              items: result.items,
              total: result.total,
            },
          });
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        setSnapshot({
          key,
          state: {
            status: 'error',
            items: [],
            total: 0,
            ...(error instanceof HttpError &&
            (error.status === 401 || error.status === 403)
              ? { accessDenied: error.status }
              : {}),
            ...(error instanceof HttpError && error.requestId
              ? { requestId: error.requestId }
              : {}),
          },
        });
      });
    return () => controller.abort();
  }, [page, page_size, name, provider_type, status, key]);

  return snapshot?.key === key
    ? snapshot.state
    : { status: 'loading' as const, items: [], total: 0 };
}
