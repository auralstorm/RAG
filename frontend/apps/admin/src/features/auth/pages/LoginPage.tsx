import { useEffect, useRef, useState } from 'react';
import { Link, Navigate } from 'react-router';
import { Alert, Button, Form, Input } from 'antd';
import {
  AccessScreen,
  SessionBoundary,
  useSessionState,
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
  const [form] = Form.useForm<LoginCredentials>();
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

  async function handleLogin(values: LoginCredentials) {
    if (!onLogin || request.current) return;
    const controller = new AbortController();
    request.current = controller;
    setSubmitting(true);
    setError(false);
    try {
      await onLogin(values, controller.signal);
    } catch {
      if (!controller.signal.aborted) setError(true);
    } finally {
      if (request.current === controller) {
        request.current = null;
        setSubmitting(false);
        form.resetFields(['password']);
      }
    }
  }

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
      {!onLogin ? (
        <Alert
          type="info"
          showIcon
          title="管理员登录暂未开放，请联系系统负责人。"
        />
      ) : null}
      {hasError ? (
        <Alert
          type="error"
          showIcon
          title="暂时无法登录，请重试或联系系统负责人。"
        />
      ) : null}
      <Form<LoginCredentials>
        form={form}
        name="admin-login"
        layout="vertical"
        requiredMark={false}
        disabled={!onLogin || isSubmitting}
        clearOnDestroy
        onFinish={(values) => {
          void handleLogin(values);
        }}
      >
        <Form.Item
          name="username"
          label="管理员账号"
          rules={[
            { required: true, whitespace: true, message: '请输入管理员账号。' },
          ]}
        >
          <Input autoComplete="username" size="large" />
        </Form.Item>
        <Form.Item
          name="password"
          label="密码"
          rules={[{ required: true, message: '请输入密码。' }]}
        >
          <Input.Password autoComplete="current-password" size="large" />
        </Form.Item>
        <Button
          type="primary"
          size="large"
          block
          htmlType="submit"
          aria-label="登录"
          disabled={!onLogin || isSubmitting}
          loading={isSubmitting}
        >
          登录
        </Button>
      </Form>
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
