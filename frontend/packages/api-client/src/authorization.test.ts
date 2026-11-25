import { expect, it, vi } from 'vitest';
import { createApiClient } from './index';

const SUBJECT = '12345678-1234-4321-8123-123456789abc';
function capabilities() {
  return {
    subject_id: SUBJECT,
    application: 'admin',
    policy_version: 'p1',
    roles: [],
    permission_codes: ['dashboard.read'],
  };
}
function client(payload: unknown) {
  const fetcher = vi
    .fn<typeof fetch>()
    .mockResolvedValue(new Response(JSON.stringify(payload)));
  return {
    api: createApiClient('https://api.example/backend/', fetcher),
    fetcher,
  };
}

it('reads subject-bound permissions using cookie credentials and the configured proxy prefix', async () => {
  const { api, fetcher } = client(capabilities());
  await expect(
    api.authorization.capabilities(
      'admin',
      SUBJECT,
      new AbortController().signal,
    ),
  ).resolves.toEqual(capabilities());
  expect(String(fetcher.mock.calls[0]?.[0])).toBe(
    'https://api.example/backend/api/v1/authorization/admin/me',
  );
  expect(fetcher.mock.calls[0]?.[1]).toMatchObject({
    credentials: 'include',
    cache: 'no-store',
  });
});

it.each([
  { subject_id: undefined },
  { subject_id: '22345678-1234-4321-8123-123456789abc' },
  { application: 'chat' },
  { policy_version: '' },
  { policy_version: '<private-diagnostic>' },
  { permission_codes: ['*'] },
  { permission_codes: ['dashboard.read', 'dashboard.read'] },
  { permission_codes: [true] },
  { permission_codes: undefined },
  { roles: [{}] },
  { unexpected: true },
  {
    roles: [
      {
        id: SUBJECT,
        schema_version: '1.0',
        code: 'SUPER_ADMIN',
        name: '管理员',
        is_system: false,
        protected: false,
      },
    ],
  },
  {
    roles: [
      {
        id: SUBJECT,
        schema_version: '1.0',
        code: 'CUSTOM',
        name: '自定义',
        is_system: true,
        protected: true,
      },
    ],
  },
  {
    roles: [
      {
        id: SUBJECT,
        schema_version: '1.0',
        code: 'CUSTOM',
        name: '自定义',
        is_system: false,
        protected: false,
        unexpected: true,
      },
    ],
  },
])(
  'rejects malformed or mixed-identity capability responses: %j',
  async (change) => {
    const { api } = client({ ...capabilities(), ...change });
    await expect(
      api.authorization.capabilities(
        'admin',
        SUBJECT,
        new AbortController().signal,
      ),
    ).rejects.toThrow('Invalid capability response');
  },
);

it.each(['SUPER_ADMIN', 'KB_ADMIN', 'AUDIT_READONLY', 'CUSTOM'])(
  'accepts formal role flags for %s',
  async (code) => {
    const system = code !== 'CUSTOM';
    const role = {
      id: SUBJECT,
      schema_version: '1.0',
      code,
      name: '角色',
      is_system: system,
      protected: system,
    };
    const { api } = client({ ...capabilities(), roles: [role] });
    await expect(
      api.authorization.capabilities(
        'admin',
        SUBJECT,
        new AbortController().signal,
      ),
    ).resolves.toMatchObject({ roles: [role] });
  },
);
