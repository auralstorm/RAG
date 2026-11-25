import { useEffect, useRef, useState } from 'react';
import { Link, Navigate } from 'react-router';
import { Alert, Button } from 'antd';
import {
  AccessScreen,
  SessionBoundary,
  useSessionState,
  useSessionActions,
  CredentialForm,
} from '@enterprise-rag/ui';

interface LoginPageProps {
  readonly onLogin?: (signal: AbortSignal) => Promise<void>;
}

export function LoginPage({ onLogin }: LoginPageProps) {
  const session = useSessionState();
  const actions = useSessionActions();
  const request = useRef<AbortController | null>(null);
  const [isSubmitting, setSubmitting] = useState(false);
  const [hasError, setError] = useState(false);
  useEffect(
    () => () => {
      request.current?.abort();
      request.current = null;
    },
    [],
  );

  async function handleLogin() {
    if (!onLogin || request.current) return;
    const controller = new AbortController();
    request.current = controller;
    setSubmitting(true);
    setError(false);
    try {
      await onLogin(controller.signal);
    } catch {
      if (!controller.signal.aborted) setError(true);
    } finally {
      if (request.current === controller) {
        request.current = null;
        setSubmitting(false);
      }
    }
  }

  const loginForm = (
    <AccessScreen
      title="登录企业知识助手"
      description="使用企业账号查阅知识，获取可追溯的回答。"
      footer={
        import.meta.env.DEV && import.meta.env.MODE === 'development' ? (
          <Link to="/preview">打开开发预览</Link>
        ) : (
          '账号或访问权限有问题，请联系管理员。'
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
      {!onLogin && actions.mode !== 'local' ? (
        <Alert type="info" showIcon title="企业登录暂未开放，请联系管理员。" />
      ) : null}
      {hasError ? (
        <Alert
          type="error"
          showIcon
          title="暂时无法登录，请重试或联系管理员。"
        />
      ) : null}
      {actions.mode === 'local' ? (
        <CredentialForm accountLabel="测试账号" onLogin={actions.login} />
      ) : (
        <Button
          type="primary"
          size="large"
          block
          aria-label="使用企业账号登录"
          disabled={!onLogin}
          loading={isSubmitting}
          onClick={() => {
            void handleLogin();
          }}
        >
          使用企业账号登录
        </Button>
      )}
    </AccessScreen>
  );
  return (
    <SessionBoundary
      loginFallback={loginForm}
      recoveryAction={<a href="/login">重新加载</a>}
    >
      <Navigate to="/chat" replace />
    </SessionBoundary>
  );
}
