import '@testing-library/jest-dom/vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { apiClient } from '@admin/api/apiClient';
import { AppProviders } from '@admin/app/AppProviders';
import { HttpError } from '@enterprise-rag/api-client';

import { DashboardPage } from './DashboardPage';

function renderDashboard() {
  return render(
    <AppProviders>
      <DashboardPage />
    </AppProviders>,
  );
}

describe('API connection table', () => {
  it('starts empty and makes no request until the user asks', () => {
    const request = vi.spyOn(apiClient, 'getLiveness');
    renderDashboard();
    expect(
      screen.getByText('尚未检查服务连接，请点击“检查连接”。'),
    ).toBeVisible();
    expect(request).not.toHaveBeenCalled();
  });

  it('shows loading, prevents duplicate requests and renders only a confirmed result', async () => {
    let finish: (() => void) | undefined;
    const request = vi.spyOn(apiClient, 'getLiveness').mockImplementation(
      () =>
        new Promise((resolve) => {
          finish = () => resolve({ status: 'ok' });
        }),
    );
    renderDashboard();
    fireEvent.click(screen.getByRole('button', { name: '检查连接' }));
    expect(screen.getByRole('status')).toHaveTextContent('正在检查服务连接');
    fireEvent.click(screen.getByRole('button', { name: '检查连接' }));
    expect(request).toHaveBeenCalledTimes(1);
    finish?.();
    await screen.findByRole('cell', { name: '可连接' });
    expect(screen.getByRole('rowheader', { name: '后端 API' })).toBeVisible();
  });

  it('clears stale results after failure, preserves request ID and supports retry', async () => {
    const request = vi
      .spyOn(apiClient, 'getLiveness')
      .mockResolvedValueOnce({ status: 'ok' })
      .mockRejectedValueOnce(
        new HttpError(503, {
          code: 'SERVICE_UNAVAILABLE',
          message: 'private-provider-diagnostic',
          request_id: '12345678-1234-4321-8123-123456789abc',
          retryable: true,
        }),
      )
      .mockResolvedValueOnce({ status: 'ok' });
    renderDashboard();
    fireEvent.click(screen.getByRole('button', { name: '检查连接' }));
    await screen.findByRole('cell', { name: '可连接' });
    fireEvent.click(screen.getByRole('button', { name: '检查连接' }));
    await screen.findByText('暂时无法连接服务，请重试。');
    expect(screen.getByText(/请求编号：12345678/)).toBeVisible();
    expect(
      screen.queryByText('private-provider-diagnostic'),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole('cell', { name: '可连接' }),
    ).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '重试连接' }));
    await screen.findByRole('cell', { name: '可连接' });
    expect(request).toHaveBeenCalledTimes(3);
  });

  it('aborts on unmount and ignores a late response', async () => {
    let finish: (() => void) | undefined;
    const request = vi.spyOn(apiClient, 'getLiveness').mockImplementation(
      () =>
        new Promise((resolve) => {
          finish = () => resolve({ status: 'ok' });
        }),
    );
    const { unmount } = renderDashboard();
    fireEvent.click(screen.getByRole('button', { name: '检查连接' }));
    const signal = request.mock.calls[0]?.[0];
    unmount();
    expect(signal?.aborted).toBe(true);
    finish?.();
    renderDashboard();
    await waitFor(() =>
      expect(screen.queryByText('可连接')).not.toBeInTheDocument(),
    );
    expect(
      screen.getByText('尚未检查服务连接，请点击“检查连接”。'),
    ).toBeVisible();
  });
});
