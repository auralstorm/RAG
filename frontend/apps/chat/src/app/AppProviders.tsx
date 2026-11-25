import type { ReactNode } from 'react';
import { XProvider } from '@ant-design/x';
import zhCNX from '@ant-design/x/locale/zh_CN';
import zhCN from 'antd/locale/zh_CN';

const LOCALE = { ...zhCN, ...zhCNX };
const THEME = {
  token: { colorPrimary: '#1765ad', colorTextPlaceholder: '#6b7280' },
};

export function AppProviders({ children }: { readonly children: ReactNode }) {
  return (
    <XProvider locale={LOCALE} theme={THEME}>
      {children}
    </XProvider>
  );
}
