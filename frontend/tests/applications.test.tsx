import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { App as ChatApp } from '../apps/chat/src/App';
import { App as AdminApp } from '../apps/admin/src/App';

describe.each([
  ['员工端', ChatApp, '新对话'],
  ['管理端', AdminApp, '企业知识管理'],
] as const)('%s application', (_label, App, title) => {
  it('renders its own accessible heading and main landmark', () => {
    render(<App />);
    expect(
      screen.getByRole('heading', { level: 1, name: title }),
    ).toBeVisible();
    expect(screen.getByRole('main')).toBeInTheDocument();
  });
});

it('supports asking, stopping, retrying, feedback and isolated session switching', async () => {
  render(<ChatApp />);
  const input = screen.getByRole('textbox', { name: '输入你的 IT 问题' });
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
});
