import { Result } from 'antd';
import type { ReactNode } from 'react';

import type { SessionStatusProps } from '@enterprise-rag/ui';

import styles from '../layouts/admin.module.css';

import { EnterpriseBrand } from './EnterpriseBrand';

export function AdminStatusScreen({
  title,
  description,
  status = 'info',
  children,
}: {
  readonly title: string;
  readonly description: string;
  readonly status?: 'info' | '403' | '404' | '500';
  readonly children?: ReactNode;
}) {
  return (
    <div className={styles.entry}>
      <header className={styles.entryHeader}>
        <EnterpriseBrand />
      </header>
      <main className={styles.status}>
        <Result
          status={status}
          title={<h1 className={styles.statusTitle}>{title}</h1>}
          subTitle={description}
          extra={<div className={styles.recovery}>{children}</div>}
        />
      </main>
    </div>
  );
}

export function AdminSessionStatus({ kind, ...props }: SessionStatusProps) {
  return (
    <AdminStatusScreen
      {...props}
      status={kind === 'error' ? '500' : kind === 'forbidden' ? '403' : 'info'}
    />
  );
}
