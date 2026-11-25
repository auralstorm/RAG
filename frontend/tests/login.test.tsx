import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { describe, expect, it, vi } from 'vitest';
import { SessionProvider } from '@enterprise-rag/ui';
import { LoginPage as ChatLoginPage } from '../apps/chat/src/features/auth/pages/LoginPage';
import { LoginPage as AdminLoginPage } from '../apps/admin/src/features/auth/pages/LoginPage';
import { AppProviders as ChatProviders } from '../apps/chat/src/app/AppProviders';
import { AppProviders as AdminProviders } from '../apps/admin/src/app/AppProviders';

describe('login forms', () => {
  it('requires admin credentials and does not persist the password', async () => {
    const onLogin = vi.fn().mockResolvedValue(undefined);
    render(
      <MemoryRouter>
        <AdminProviders>
          <AdminLoginPage onLogin={onLogin} />
        </AdminProviders>
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByRole('button', { name: '登录' }));
    await screen.findByText('请输入管理员账号。');
    expect(onLogin).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText('管理员账号'), {
      target: { value: 'test-admin' },
    });
    fireEvent.change(screen.getByLabelText('密码', { exact: true }), {
      target: { value: 'transient-fixture-password' },
    });
    fireEvent.click(screen.getByRole('button', { name: '登录' }));
    await waitFor(() => expect(onLogin).toHaveBeenCalledTimes(1));
    await waitFor(() =>
      expect(screen.getByLabelText('密码', { exact: true })).toHaveValue(''),
    );
    expect(localStorage.length).toBe(0);
    expect(sessionStorage.length).toBe(0);
    expect(
      screen.getByRole('heading', { name: '登录企业知识管理' }),
    ).toBeInTheDocument();
  });

  it('keeps successful SSO initiation separate from an authenticated session', async () => {
    const onLogin = vi.fn().mockResolvedValue(undefined);
    render(
      <MemoryRouter>
        <ChatProviders>
          <ChatLoginPage onLogin={onLogin} />
        </ChatProviders>
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByRole('button', { name: '使用企业账号登录' }));
    await waitFor(() => expect(onLogin).toHaveBeenCalledTimes(1));
    expect(
      screen.getByRole('heading', { name: '登录企业知识助手' }),
    ).toBeInTheDocument();
  });

  it('prevents duplicate login and aborts a pending request on unmount', async () => {
    const onLogin = vi
      .fn<(signal: AbortSignal) => Promise<void>>()
      .mockReturnValue(new Promise(() => {}));
    const { unmount } = render(
      <MemoryRouter>
        <ChatProviders>
          <ChatLoginPage onLogin={onLogin} />
        </ChatProviders>
      </MemoryRouter>,
    );
    const button = screen.getByRole('button', { name: '使用企业账号登录' });
    fireEvent.click(button);
    fireEvent.click(button);
    expect(onLogin).toHaveBeenCalledTimes(1);
    const signal = onLogin.mock.calls[0]?.[0];
    unmount();
    expect(signal?.aborted).toBe(true);
  });

  it('shows a recoverable failure without echoing credential or provider errors', async () => {
    render(
      <MemoryRouter>
        <ChatProviders>
          <SessionProvider state={{ status: 'anonymous' }}>
            <ChatLoginPage
              onLogin={async () => {
                throw new Error('private-provider-error');
              }}
            />
          </SessionProvider>
        </ChatProviders>
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByRole('button', { name: '使用企业账号登录' }));
    await screen.findByText('暂时无法登录，请重试或联系管理员。');
    expect(
      screen.queryByText('private-provider-error'),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: '使用企业账号登录' }),
    ).toBeEnabled();
  });
});
