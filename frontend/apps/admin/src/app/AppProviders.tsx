import type { ReactNode } from 'react';
import { ConfigProvider } from 'antd';
import zhCN from 'antd/locale/zh_CN';

const THEME = {
  token: {
    colorPrimary: '#1765ad',
    borderRadius: 10,
    colorTextPlaceholder: '#6b7280',
  },
};
export function AppProviders({ children }: { readonly children: ReactNode }) {
  return (
    <ConfigProvider locale={zhCN} theme={THEME}>
      {children}
    </ConfigProvider>
  );
}
