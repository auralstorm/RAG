import { Card, Typography } from 'antd';
import type { ReactNode } from 'react';
import styles from './ApplicationShell.module.css';

interface ApplicationShellProps {
  readonly title: string;
  readonly description: string;
  readonly children: ReactNode;
}

export function ApplicationShell({
  title,
  description,
  children,
}: ApplicationShellProps) {
  return (
    <main className={styles.shell}>
      <header>
        <Typography.Text type="secondary">EnterpriseRag</Typography.Text>
        <Typography.Title level={1}>{title}</Typography.Title>
        <Typography.Paragraph>{description}</Typography.Paragraph>
      </header>
      <Card>{children}</Card>
    </main>
  );
}
