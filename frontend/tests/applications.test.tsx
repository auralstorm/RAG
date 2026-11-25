import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { createMemoryRouter } from 'react-router';
import { createChatRoutes } from '@chat/routes/routes';
import { createAdminRoutes } from '@admin/routes/routes';
import { ChatWorkspacePage } from '@chat/pages/chat/ChatWorkspacePage';
import { App as ChatApp } from '@chat/app/App';
import { App as AdminApp } from '@admin/app/App';
import { AppProviders } from '@chat/app/AppProviders';
import { ChatPage } from '@chat/modules/chat';
import { waitForRouter } from './router';

const mockReplySource = {
  notice: 'test reply source',
  async *streamReply() {
    yield '网络与远程访问';
  },
};

describe.each([
  ['员工端', ChatApp, '登录企业知识助手', createChatRoutes],
  ['管理端', AdminApp, '登录企业知识管理', createAdminRoutes],
] as const)('%s application', (_label, App, title, createRoutes) => {
  it('redirects to its own accessible login page', async () => {
    const router = createMemoryRouter(createRoutes(), {
      initialEntries: ['/'],
    });
    render(<App router={router} />);
    await waitForRouter(
      router,
      (state) =>
        state.location.pathname === '/login' &&
        state.navigation.state === 'idle',
    );
    await screen.findByRole('heading', { level: 1, name: title });
    expect(router.state.location.pathname).toBe('/login');
    expect(
      screen.getByRole('heading', { level: 1, name: title }),
    ).toBeVisible();
    expect(screen.getByRole('main')).toBeInTheDocument();
  });
});

it('shows the unavailable interface state with submission disabled', async () => {
  render(
    <AppProviders>
      <ChatWorkspacePage />
    </AppProviders>,
  );
  await waitFor(() => {
    expect(screen.getAllByText('知识问答接口尚未接入').length).toBeGreaterThan(
      0,
    );
  });
  expect(
    screen.getByRole('textbox', { name: '输入你的 IT 问题' }),
  ).toBeDisabled();
  expect(screen.getByRole('button', { name: '发送问题' })).toBeDisabled();
  expect(
    screen
      .getAllByRole('button', { name: '如何申请 VPN 访问？' })
      .every((button) => button.hasAttribute('disabled')),
  ).toBe(true);
  expect(
    screen.queryByText('开发环境 · 回答为模拟内容'),
  ).not.toBeInTheDocument();
});

it('shows a safe generation error without exposing source details', async () => {
  render(
    <AppProviders>
      <ChatPage
        replySource={{
          notice: '',
          async *streamReply() {
            yield '部分回答';
            throw new Error('private-source-details');
          },
        }}
      />
    </AppProviders>,
  );
  fireEvent.change(screen.getByRole('textbox', { name: '输入你的 IT 问题' }), {
    target: { value: 'test question' },
  });
  fireEvent.click(screen.getByRole('button', { name: '发送问题' }));
  await waitFor(() =>
    expect(screen.getByRole('status')).toHaveTextContent('回答生成失败'),
  );
  expect(screen.getByText('部分回答')).toBeInTheDocument();
  expect(screen.getByText('回答生成失败，请重试。')).toBeInTheDocument();
  expect(screen.queryByText('private-source-details')).not.toBeInTheDocument();
  expect(screen.getByRole('button', { name: '重新生成' })).toBeEnabled();
});

it('supports asking, stopping, retrying, feedback and isolated session switching', async () => {
  render(
    <AppProviders>
      <ChatPage replySource={mockReplySource} />
    </AppProviders>,
  );
  const input = screen.getByRole('textbox', { name: '输入你的 IT 问题' });
  expect(screen.getByRole('button', { name: '发送问题' })).toBeDisabled();
  fireEvent.change(input, { target: { value: '如何申请 VPN 访问？' } });
  fireEvent.click(screen.getByRole('button', { name: '发送问题' }));
  expect(input).toHaveValue('');
  fireEvent.click(screen.getByRole('button', { name: '停止生成' }));
  expect(screen.getByRole('status')).toHaveTextContent('已停止生成');
  fireEvent.click(screen.getByRole('button', { name: '重新生成' }));
  await waitFor(() => {
    expect(screen.getByRole('status')).toHaveTextContent('回答已完成');
  });
  expect(screen.getByText('网络与远程访问')).toBeInTheDocument();
  const feedback = screen.getByRole('button', { name: '有帮助' });
  fireEvent.click(feedback);
  expect(feedback).toHaveAttribute('aria-pressed', 'true');
  fireEvent.click(feedback);
  expect(feedback).toHaveAttribute('aria-pressed', 'false');
  fireEvent.click(screen.getByRole('button', { name: /新建对话/ }));
  expect(screen.queryByText('网络与远程访问')).not.toBeInTheDocument();
  fireEvent.change(screen.getByRole('textbox', { name: '输入你的 IT 问题' }), {
    target: { value: '如何提交 IT 工单？' },
  });
  fireEvent.click(screen.getByRole('button', { name: '发送问题' }));
  fireEvent.click(screen.getByRole('button', { name: '停止生成' }));
  fireEvent.click(
    within(screen.getByRole('complementary')).getByRole('button', {
      name: '如何申请 VPN 访问？',
    }),
  );
  expect(screen.getAllByText('网络与远程访问')).toHaveLength(1);
  expect(screen.getAllByRole('button', { name: '重新生成' })).toHaveLength(1);
}, 10_000);
