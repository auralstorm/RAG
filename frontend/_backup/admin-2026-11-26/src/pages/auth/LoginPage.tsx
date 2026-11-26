import { Alert } from 'antd';
import { Link, Navigate } from 'react-router';

import { AdminSessionStatus } from '@admin/components/AdminStatusScreen';
import { EnterpriseBrand } from '@admin/components/EnterpriseBrand';
import styles from '@admin/layouts/admin.module.css';
import type { LoginCredentials } from '@admin/modules/auth';
import {
  CredentialForm,
  SessionBoundary,
  SessionLogoutButton,
  useSessionState,
  useSessionActions,
} from '@enterprise-rag/ui';

interface LoginPageProps {
  readonly onLogin?: (
    credentials: LoginCredentials,
    signal: AbortSignal,
  ) => Promise<void>;
}

export function LoginPage({ onLogin }: LoginPageProps) {
  const session = useSessionState();
  const actions = useSessionActions();
  const login = onLogin ?? actions.login;
  const loginForm = (
    <div className={styles.entry}>
      <header className={styles.entryHeader}>
        <EnterpriseBrand />
      </header>
      <main className={styles.login}>
        <h1>登录企业知识管理</h1>
        <p className={styles.description}>
          使用管理员账号进入知识与平台管理工作台。
        </p>
        <div className={styles.loginBody}>
          {session.status === 'anonymous' && session.reason === 'expired' ? (
            <Alert type="warning" showIcon title="登录已过期，请重新登录。" />
          ) : null}
          {actions.mode === 'local' ? (
            <Alert
              type="info"
              showIcon
              title="本地测试身份源"
              description="仅用于开发与测试，不代表企业 SSO 已接入。"
            />
          ) : null}
          {!login ? (
            <Alert
              type="info"
              showIcon
              title="管理员登录暂未开放，请联系系统负责人。"
            />
          ) : null}
          <CredentialForm accountLabel="管理员账号" onLogin={login} />
        </div>
        <footer className={styles.entryFooter}>
          {import.meta.env.DEV && import.meta.env.MODE === 'development' ? (
            <Link to="/preview">打开开发预览</Link>
          ) : (
            '账号或访问权限有问题，请联系系统负责人。'
          )}
        </footer>
      </main>
    </div>
  );
  return (
    <SessionBoundary
      loginFallback={loginForm}
      renderStatus={(props) => <AdminSessionStatus {...props} />}
      recoveryAction={
        <>
          <SessionLogoutButton />
          <a href="/login">重新加载</a>
        </>
      }
    >
      <Navigate to="/admin" replace />
    </SessionBoundary>
  );
}
