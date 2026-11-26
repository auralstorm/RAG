import { theme } from 'antd';
import type { CSSProperties, ReactNode } from 'react';

import styles from './AccessScreen.module.css';

interface AccessScreenProps {
  readonly title: string;
  readonly description: string;
  readonly children?: ReactNode;
  readonly footer?: ReactNode;
}

export function AccessScreen({
  title,
  description,
  children,
  footer,
}: AccessScreenProps) {
  const { token } = theme.useToken();
  const palette: CSSProperties & Record<`--access-${string}`, string> = {
    '--access-background': token.colorBgLayout,
    '--access-surface': token.colorBgContainer,
    '--access-text': token.colorText,
    '--access-muted': token.colorTextSecondary,
    '--access-border': token.colorBorderSecondary,
    '--access-accent': token.colorPrimary,
    '--access-selection': token.colorPrimaryBg,
  };
  return (
    <div className={styles.screen} style={palette}>
      <header className={styles.brand}>EnterpriseRag</header>
      <main className={styles.content}>
        <h1>{title}</h1>
        <p className={styles.description}>{description}</p>
        <div className={styles.body}>{children}</div>
        {footer ? <footer className={styles.footer}>{footer}</footer> : null}
      </main>
    </div>
  );
}
