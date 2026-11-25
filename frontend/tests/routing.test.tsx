import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { createMemoryRouter } from 'react-router';
import { describe, expect, it, vi } from 'vitest';
import type { SessionState } from '@enterprise-rag/shared';
import { App as ChatApp } from '../apps/chat/src/app/App';
import { App as AdminApp } from '../apps/admin/src/app/App';
import { createChatRoutes } from '../apps/chat/src/routes/routes';
import { createAdminRoutes } from '../apps/admin/src/routes/routes';
import { apiClient as adminApiClient } from '../apps/admin/src/app/api-client';

it('uses operation permissions for Admin access and leaves Chat accessible without a KB grant', async () => {
  const session: SessionState = {
    status: 'authenticated',
    subjectId: 'fixture-subject',
    canAccessApplication: true,
    authorization: { policyVersion: 'p1', permissionCodes: [] },
  };
  const logout = vi.fn<() => Promise<void>>().mockResolvedValue();
  const admin = render(
    <AdminApp
      router={createMemoryRouter(createAdminRoutes(), {
        initialEntries: ['/admin'],
      })}
      session={session}
      actions={{ mode: 'local', logout }}
    />,
  );
  await screen.findByRole('heading', { name: '暂无访问权限' });
  expect(
    screen.queryByRole('button', { name: '检查连接' }),
  ).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: '退出登录' }));
  expect(logout).toHaveBeenCalledTimes(1);
  admin.unmount();
  const chatRouter = createMemoryRouter(createChatRoutes(), {
    initialEntries: ['/chat'],
  });
  // Wait for the router's actual lazy initialization before asserting permissions.
  await new Promise<void>((resolve) => {
    if (chatRouter.state.initialized) {
      resolve();
      return;
    }
    const unsubscribe = chatRouter.subscribe((state) => {
      if (state.initialized) {
        unsubscribe();
        resolve();
      }
    });
  });
  render(<ChatApp router={chatRouter} session={session} />);
  await screen.findByRole('heading', { name: '新对话' });
});

it('unmounts Admin content when current permissions are revoked', async () => {
  vi.spyOn(adminApiClient, 'getLiveness').mockResolvedValue({ status: 'ok' });
  const router = createMemoryRouter(createAdminRoutes(), {
    initialEntries: ['/admin'],
  });
  const session: SessionState = {
    status: 'authenticated',
    subjectId: 'fixture-subject',
    canAccessApplication: true,
    authorization: { policyVersion: 'p1', permissionCodes: ['dashboard.read'] },
  };
  const { rerender } = render(<AdminApp router={router} session={session} />);
  await screen.findByRole('button', { name: '检查连接' });
  fireEvent.click(screen.getByRole('button', { name: '检查连接' }));
  await screen.findByRole('cell', { name: '可连接' });
  rerender(
    <AdminApp
      router={router}
      session={{
        ...session,
        authorization: {
          policyVersion: 'p2',
          permissionCodes: ['dashboard.read'],
        },
      }}
    />,
  );
  await screen.findByText('尚未检查服务连接，请点击“检查连接”。');
  expect(
    screen.queryByRole('cell', { name: '可连接' }),
  ).not.toBeInTheDocument();
  rerender(
    <AdminApp
      router={router}
      session={{
        ...session,
        authorization: { policyVersion: 'p3', permissionCodes: [] },
      }}
    />,
  );
  await screen.findByRole('heading', { name: '暂无访问权限' });
  expect(
    screen.queryByRole('button', { name: '检查连接' }),
  ).not.toBeInTheDocument();
});

describe.each([
  ['Chat', ChatApp, createChatRoutes, '/chat', '新对话'],
  ['Admin', AdminApp, createAdminRoutes, '/admin', '企业知识管理'],
] as const)(
  '%s route access',
  (_label, App, createRoutes, protectedPath, heading) => {
    it.each([
      [{ status: 'checking' }, '正在确认登录状态'],
      [{ status: 'forbidden' }, '暂无访问权限'],
      [
        {
          status: 'authenticated',
          subjectId: 'fixture-subject',
          canAccessApplication: false,
          authorization: {
            policyVersion: 'p1',
            permissionCodes: ['dashboard.read'],
          },
        },
        '暂无访问权限',
      ],
      [
        { status: 'error', requestId: 'request-reference' },
        '暂时无法确认登录状态',
      ],
      [
        {
          status: 'authenticated',
          subjectId: '',
          canAccessApplication: true,
          authorization: { policyVersion: 'p1', permissionCodes: [] },
        },
        '暂无访问权限',
      ],
    ] satisfies [SessionState, string][])(
      'hides protected content in %j state',
      async (session, expectedHeading) => {
        const router = createMemoryRouter(createRoutes(), {
          initialEntries: [protectedPath],
        });
        render(<App router={router} session={session} />);
        await screen.findByRole('heading', { name: expectedHeading });
        expect(
          screen.queryByRole('heading', { name: heading }),
        ).not.toBeInTheDocument();
      },
    );

    it('redirects expired sessions to login with a clear message', async () => {
      const router = createMemoryRouter(createRoutes(), {
        initialEntries: [protectedPath],
      });
      render(
        <App
          router={router}
          session={{ status: 'anonymous', reason: 'expired' }}
        />,
      );
      await screen.findByText('登录已过期，请重新登录。');
      expect(router.state.location.pathname).toBe('/login');
      expect(
        screen.queryByRole('heading', { name: heading }),
      ).not.toBeInTheDocument();
    });

    it('uses a trusted supplied session and removes protected UI when it expires', async () => {
      const router = createMemoryRouter(createRoutes(), {
        initialEntries: ['/login'],
      });
      const { rerender } = render(
        <App
          router={router}
          session={{
            status: 'authenticated',
            subjectId: 'fixture-subject',
            canAccessApplication: true,
            authorization: {
              policyVersion: 'p1',
              permissionCodes: ['dashboard.read'],
            },
          }}
        />,
      );
      await screen.findByRole('heading', { level: 1, name: heading });
      expect(router.state.location.pathname).toBe(protectedPath);
      rerender(
        <App
          router={router}
          session={{ status: 'anonymous', reason: 'expired' }}
        />,
      );
      await screen.findByText('登录已过期，请重新登录。');
      expect(
        screen.queryByRole('heading', { name: heading }),
      ).not.toBeInTheDocument();
    });

    it('does not treat URL parameters or browser storage as a session', async () => {
      localStorage.setItem('token', 'untrusted-fixture');
      const router = createMemoryRouter(createRoutes(), {
        initialEntries: [
          `${protectedPath}?authenticated=true&next=https://example.com`,
        ],
      });
      render(<App router={router} />);
      await waitFor(() =>
        expect(router.state.location.pathname).toBe('/login'),
      );
      expect(
        screen.queryByRole('heading', { name: heading }),
      ).not.toBeInTheDocument();
      localStorage.clear();
    });
  },
);

it.each([
  [ChatApp, createChatRoutes],
  [AdminApp, createAdminRoutes],
] as const)(
  'does not expose developer preview routes in production',
  async (App, createRoutes) => {
    vi.stubEnv('DEV', false);
    vi.stubEnv('MODE', 'production');
    try {
      const router = createMemoryRouter(createRoutes(), {
        initialEntries: ['/preview'],
      });
      render(<App router={router} />);
      await screen.findByRole('heading', { name: '页面不存在' });
      expect(
        screen.queryByRole('textbox', { name: '输入你的 IT 问题' }),
      ).not.toBeInTheDocument();
      expect(screen.queryByText('打开开发预览')).not.toBeInTheDocument();
    } finally {
      vi.unstubAllEnvs();
    }
  },
);
