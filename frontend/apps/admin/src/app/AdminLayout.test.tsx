import { fireEvent, render, screen, within } from '@testing-library/react';
import { createMemoryRouter } from 'react-router';
import { expect, it, vi } from 'vitest';
import type { SessionState } from '@enterprise-rag/shared';
import { App } from './App';
import { createAdminRoutes } from '../routes/routes';
import { waitForRouter } from '../../../../tests/router';

const session: SessionState = {
  status: 'authenticated',
  subjectId: 'fixture-subject',
  canAccessApplication: true,
  authorization: { policyVersion: 'p1', permissionCodes: ['dashboard.read'] },
};

it('keeps navigation, breadcrumbs and the current route consistent and supports collapse', async () => {
  const logout = vi.fn<() => Promise<void>>().mockResolvedValue();
  const router = createMemoryRouter(createAdminRoutes(), {
    initialEntries: ['/admin'],
  });
  await waitForRouter(router);
  render(
    <App
      router={router}
      session={session}
      actions={{ mode: 'local', logout }}
    />,
  );
  await screen.findByRole('heading', { level: 1, name: '企业知识管理' });
  const navigation = screen.getByRole('navigation', { name: '管理导航' });
  const currentLink = within(navigation).getByRole('link', {
    name: '服务概览',
  });
  expect(currentLink).toHaveAttribute('aria-current', 'page');
  expect(currentLink).toHaveAttribute('href', '/admin');
  expect(screen.getByRole('group', { name: '页面位置' })).toHaveTextContent(
    '服务概览',
  );
  fireEvent.click(screen.getByRole('button', { name: '收起导航' }));
  expect(screen.getByRole('button', { name: '展开导航' })).toHaveAttribute(
    'aria-expanded',
    'false',
  );
  fireEvent.click(screen.getByRole('button', { name: '展开导航' }));
  expect(screen.getByRole('button', { name: '收起导航' })).toHaveAttribute(
    'aria-expanded',
    'true',
  );
  fireEvent.click(currentLink);
  expect(router.state.location.pathname).toBe('/admin');
  fireEvent.click(screen.getByRole('button', { name: '退出登录' }));
  expect(logout).toHaveBeenCalledTimes(1);
}, 10_000);

it('removes navigation as well as page content when permissions are revoked', async () => {
  const router = createMemoryRouter(createAdminRoutes(), {
    initialEntries: ['/admin'],
  });
  await waitForRouter(router);
  const { rerender } = render(<App router={router} session={session} />);
  await screen.findByRole('heading', { name: '企业知识管理' });
  rerender(
    <App
      router={router}
      session={{
        ...session,
        authorization: { policyVersion: 'p2', permissionCodes: [] },
      }}
    />,
  );
  await screen.findByRole('heading', { name: '暂无访问权限' });
  expect(
    screen.queryByRole('navigation', { name: '管理导航' }),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByRole('button', { name: '检查连接' }),
  ).not.toBeInTheDocument();
});

it('shows a recoverable route failure without exposing the thrown diagnostic', async () => {
  const root = createAdminRoutes()[0];
  if (!root) throw new Error('Admin root route missing');
  const router = createMemoryRouter(
    [
      {
        ...root,
        loader: () => {
          throw new Error('private-route-diagnostic');
        },
      },
    ],
    { initialEntries: ['/admin'] },
  );
  await waitForRouter(router);
  render(<App router={router} session={session} />);
  await screen.findByRole('heading', { name: '页面暂时无法加载' });
  expect(screen.getByRole('button', { name: '重新加载页面' })).toBeVisible();
  expect(
    screen.queryByText('private-route-diagnostic'),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByRole('navigation', { name: '管理导航' }),
  ).not.toBeInTheDocument();
});
