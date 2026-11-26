import '@testing-library/jest-dom/vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { AppProviders } from '@chat/app/AppProviders';
import { loadReplySource } from '@chat/modules/chat';

import { ChatWorkspacePage } from './ChatWorkspacePage';

vi.mock('@chat/modules/chat', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@chat/modules/chat')>()),
  loadReplySource: vi.fn(),
}));
beforeEach(() => {
  vi.mocked(loadReplySource).mockReset();
});

describe('application initialization', () => {
  it('disables submission while the reply source is loading', () => {
    vi.mocked(loadReplySource).mockReturnValue(new Promise(() => {}));
    render(
      <AppProviders>
        <ChatWorkspacePage />
      </AppProviders>,
    );
    expect(screen.getByText('正在初始化问答服务')).toBeInTheDocument();
    expect(
      screen.getByRole('textbox', { name: '输入你的 IT 问题' }),
    ).toBeDisabled();
  });

  it('shows initialization failure without exposing implementation errors', async () => {
    vi.mocked(loadReplySource).mockRejectedValue(
      new Error('private-module-details'),
    );
    render(
      <AppProviders>
        <ChatWorkspacePage />
      </AppProviders>,
    );
    await waitFor(() =>
      expect(
        screen.getByText('问答服务初始化失败，请刷新页面重试。'),
      ).toBeInTheDocument(),
    );
    expect(
      screen.getByRole('textbox', { name: '输入你的 IT 问题' }),
    ).toBeDisabled();
    expect(
      screen.queryByText('private-module-details'),
    ).not.toBeInTheDocument();
  });
});
