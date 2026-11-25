import { Link, Navigate } from 'react-router';
import { Alert } from 'antd';
import {
  AccessScreen,
  CredentialForm,
  SessionBoundary,
  useSessionState,
  useSessionActions,
} from '@enterprise-rag/ui';
import type { LoginCredentials } from '../types';

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
    <AccessScreen
      title="登录企业知识管理"
      description="使用管理员账号进入知识与平台管理工作台。"
      footer={
        import.meta.env.DEV && import.meta.env.MODE === 'development' ? (
          <Link to="/preview">打开开发预览</Link>
        ) : (
          '账号或访问权限有问题，请联系系统负责人。'
        )
      }
    >
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
    </AccessScreen>
  );
  return (
    <SessionBoundary
      loginFallback={loginForm}
      recoveryAction={<a href="/login">重新加载</a>}
    >
      <Navigate to="/admin" replace />
    </SessionBoundary>
  );
}
