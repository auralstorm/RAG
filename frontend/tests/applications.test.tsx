import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { App as ChatApp } from '../apps/chat/src/App';
import { App as AdminApp } from '../apps/admin/src/App';

describe.each([
  ['员工端', ChatApp, '企业知识助手'],
  ['管理端', AdminApp, '企业知识管理'],
] as const)('%s application', (_label, App, title) => {
  it('renders its own accessible heading through the shared UI package', () => {
    render(<App />);
    expect(
      screen.getByRole('heading', { level: 1, name: title }),
    ).toBeVisible();
    expect(screen.getByRole('main')).toBeInTheDocument();
  });
});
