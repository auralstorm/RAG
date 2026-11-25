import type { CSSProperties, ReactNode } from 'react';
import { ConfigProvider, theme } from 'antd';
import zhCN from 'antd/locale/zh_CN';

const THEME = {
  token: {
    colorPrimary: '#1765ad',
    borderRadius: 8,
    colorTextPlaceholder: '#6b7280',
  },
};

function AdminTheme({ children }: { readonly children: ReactNode }) {
  const { token } = theme.useToken();
  const palette: CSSProperties & Record<`--admin-${string}`, string> = {
    '--admin-primary': token.colorPrimary,
    '--admin-text': token.colorText,
    '--admin-muted': token.colorTextSecondary,
    '--admin-background': token.colorBgLayout,
    '--admin-surface': token.colorBgContainer,
    '--admin-border': token.colorBorderSecondary,
    '--admin-selection': token.colorPrimaryBg,
  };
  return <div style={palette}>{children}</div>;
}
export function AppProviders({ children }: { readonly children: ReactNode }) {
  return (
    <ConfigProvider locale={zhCN} theme={THEME}>
      <AdminTheme>{children}</AdminTheme>
    </ConfigProvider>
  );
}
