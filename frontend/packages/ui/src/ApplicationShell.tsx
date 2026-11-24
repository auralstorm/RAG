import Card from 'antd/es/card';
import ConfigProvider from 'antd/es/config-provider';
import Typography from 'antd/es/typography';
import type { ReactNode } from 'react';
import styles from './ApplicationShell.module.css';

interface ApplicationShellProps {
  readonly title: string;
  readonly description: string;
  readonly children: ReactNode;
}

const theme = { token: { colorPrimary: '#1765ad', borderRadius: 10 } };

export function ApplicationShell({
  title,
  description,
  children,
}: ApplicationShellProps) {
  return (
    <ConfigProvider theme={theme}>
      <main className={styles.shell}>
        <header>
          <Typography.Text type="secondary">EnterpriseRag</Typography.Text>
          <Typography.Title level={1}>{title}</Typography.Title>
          <Typography.Paragraph>{description}</Typography.Paragraph>
        </header>
        <Card>{children}</Card>
      </main>
    </ConfigProvider>
  );
}
