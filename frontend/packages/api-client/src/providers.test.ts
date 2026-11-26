// @vitest-environment node
import { expect, it, vi } from 'vitest';
import { createApiClient, type ProviderAdminView } from './index';

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
function json(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), { status });
}

it('validates list pagination and rejects private fields or unsafe endpoints', async () => {
  const fetcher = vi
    .fn<typeof fetch>()
    .mockResolvedValueOnce(
      json({ items: [provider], total: 1, page: 1, page_size: 20 }),
    );
  const client = createApiClient('https://api.example/backend/', fetcher);
  await expect(
    client.providers.list({
      page: 1,
      page_size: 20,
      name: '测试',
      status: 'ACTIVE',
    }),
  ).resolves.toMatchObject({ total: 1 });
  expect(fetcher.mock.calls[0]?.[0]?.toString()).toContain(
    '/backend/api/v1/admin/providers?page=1&page_size=20&name=',
  );
  for (const invalid of [
    { ...provider, credential_ref: { secret_id: provider.id } },
    { ...provider, base_url: 'https://user:password@api.example' },
    { ...provider, timeout_seconds: '30' },
  ]) {
    fetcher.mockResolvedValueOnce(json(invalid));
    await expect(client.providers.get(provider.id)).rejects.toThrow(
      'Invalid provider response',
    );
  }
});

it('fetches current CSRF and sends versioned writes without replaying a failure', async () => {
  const fetcher = vi
    .fn<typeof fetch>()
    .mockResolvedValueOnce(json({ csrf_token: 'a'.repeat(64) }))
    .mockResolvedValueOnce(json({}, 409));
  const client = createApiClient('https://api.example/backend/', fetcher);
  const payload = {
    expected_policy_version: 'rbac-v1:1',
    expected_config_version: provider.config_version,
    confirm: true as const,
    clear_proxy: false,
    status: 'DISABLED' as const,
  };
  await expect(
    client.providers.update(provider.id, payload),
  ).rejects.toMatchObject({ status: 409 });
  expect(fetcher).toHaveBeenCalledTimes(2);
  const request = fetcher.mock.calls[1]?.[1];
  expect(request?.method).toBe('PATCH');
  expect(request?.credentials).toBe('include');
  expect(request?.body).toBe(JSON.stringify(payload));
  expect(new Headers(request?.headers).get('X-CSRF-Token')).toBe(
    'a'.repeat(64),
  );
});

it('does not send a write if CSRF acquisition fails', async () => {
  const fetcher = vi.fn<typeof fetch>().mockResolvedValueOnce(json({}, 401));
  const client = createApiClient('https://api.example/', fetcher);
  await expect(
    client.providers.delete(provider.id, {
      expected_policy_version: 'rbac-v1:1',
      expected_config_version: provider.config_version,
      confirm: true,
    }),
  ).rejects.toMatchObject({ status: 401 });
  expect(fetcher).toHaveBeenCalledTimes(1);
});
