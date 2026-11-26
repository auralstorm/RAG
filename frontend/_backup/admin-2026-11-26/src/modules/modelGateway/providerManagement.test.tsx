import { act, renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, expect, it, vi } from 'vitest';

import { apiClient } from '@admin/api/apiClient';
import { HttpError, type ProviderAdminView } from '@enterprise-rag/api-client';
import { SessionProvider } from '@enterprise-rag/ui';

import { useProviderList } from './useProviderList';
import { useProviderManagement } from './useProviderManagement';

const provider: ProviderAdminView = {
  schema_version: '1.0',
  id: '00000000-0000-4000-8000-000000000001',
  name: '测试供应商',
  provider_type: 'openai_compatible',
  config_version: '00000000-0000-4000-8000-000000000002',
  status: 'ACTIVE',
  has_credential: true,
  created_at: '2026-11-26T00:00:00Z',
  updated_at: '2026-11-26T00:00:00Z',
  base_url: 'https://api.example/v1',
  timeout_seconds: 30,
  proxy_configured: false,
  remarks: '',
};
const page = { items: [provider], total: 1, page: 1, page_size: 20 };
const revalidate = vi.fn<() => Promise<void>>().mockResolvedValue();
function wrapper({ children }: { readonly children: ReactNode }) {
  return (
    <SessionProvider
      state={{
        status: 'authenticated',
        subjectId: provider.id,
        canAccessApplication: true,
        authorization: {
          policyVersion: 'rbac-v1:1',
          permissionCodes: ['provider.read', 'provider.manage'],
        },
      }}
      actions={{ mode: 'platform', revalidate }}
    >
      {children}
    </SessionProvider>
  );
}
beforeEach(() => {
  vi.spyOn(apiClient.providers, 'list').mockResolvedValue(page);
  revalidate.mockClear();
});

it('cancels old list requests and ignores their late results', async () => {
  let finish: ((value: typeof page) => void) | undefined;
  const list = vi
    .spyOn(apiClient.providers, 'list')
    .mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          finish = resolve;
        }),
    )
    .mockResolvedValueOnce({ ...page, items: [], total: 0, page: 2 });
  const hook = renderHook(
    ({ number }) => useProviderList({ page: number, page_size: 20 }, 0),
    { initialProps: { number: 1 } },
  );
  hook.rerender({ number: 2 });
  await waitFor(() => expect(hook.result.current.status).toBe('ready'));
  expect(list.mock.calls[0]?.[1]?.aborted).toBe(true);
  await act(async () => {
    finish?.(page);
  });
  expect(hook.result.current.items).toEqual([]);
});

it('prevents duplicate writes and binds an edit to the viewed configuration version', async () => {
  let finish: ((value: ProviderAdminView) => void) | undefined;
  const update = vi.spyOn(apiClient.providers, 'update').mockImplementation(
    () =>
      new Promise((resolve) => {
        finish = resolve;
      }),
  );
  const hook = renderHook(useProviderManagement, { wrapper });
  await waitFor(() => expect(hook.result.current.state.status).toBe('ready'));
  act(() => {
    void hook.result.current.changeStatus(provider);
    void hook.result.current.changeStatus(provider);
  });
  expect(update).toHaveBeenCalledTimes(1);
  expect(update.mock.calls[0]?.[1]).toMatchObject({
    expected_config_version: provider.config_version,
    expected_policy_version: 'rbac-v1:1',
    status: 'DISABLED',
  });
  expect(hook.result.current.busy).toBe(true);
  await act(async () => {
    finish?.({ ...provider, status: 'DISABLED' });
  });
  expect(hook.result.current.notice?.type).toBe('success');
});

it('closes an uncertain editor, does not replay the write and rechecks the list', async () => {
  const create = vi
    .spyOn(apiClient.providers, 'create')
    .mockRejectedValue(new TypeError('private diagnostic'));
  const hook = renderHook(useProviderManagement, { wrapper });
  await waitFor(() => expect(hook.result.current.state.status).toBe('ready'));
  act(() => hook.result.current.openEditor());
  await act(async () => {
    await hook.result.current.save({
      name: '新供应商',
      provider_type: 'openai_compatible',
      base_url: provider.base_url,
      timeout_seconds: 40,
      credential: 'synthetic-key',
      confirm: true,
    });
  });
  expect(create).toHaveBeenCalledTimes(1);
  expect(hook.result.current.editor).toBe(null);
  expect(hook.result.current.notice?.text).toContain('结果尚未确认');
  expect(hook.result.current.notice?.text).not.toContain('private diagnostic');
  await waitFor(() =>
    expect(apiClient.providers.list).toHaveBeenCalledTimes(2),
  );
});

it('clears forbidden list data and requests the shared session check', async () => {
  vi.spyOn(apiClient.providers, 'list').mockRejectedValueOnce(
    new HttpError(403),
  );
  const hook = renderHook(useProviderManagement, { wrapper });
  await waitFor(() => expect(hook.result.current.accessDenied).toBe(403));
  expect(hook.result.current.state.items).toEqual([]);
  expect(hook.result.current.editor).toBe(null);
  expect(revalidate).toHaveBeenCalledTimes(1);
});

it('cancels a pending mutation when the page or current session is removed', async () => {
  let finish: ((value: ProviderAdminView) => void) | undefined;
  const update = vi.spyOn(apiClient.providers, 'update').mockImplementation(
    () =>
      new Promise((resolve) => {
        finish = resolve;
      }),
  );
  const hook = renderHook(useProviderManagement, { wrapper });
  await waitFor(() => expect(hook.result.current.state.status).toBe('ready'));
  act(() => {
    void hook.result.current.changeStatus(provider);
  });
  const signal = update.mock.calls[0]?.[2];
  expect(signal?.aborted).toBe(false);
  hook.unmount();
  expect(signal?.aborted).toBe(true);
  await act(async () => {
    finish?.(provider);
  });
  expect(update).toHaveBeenCalledTimes(1);
});
