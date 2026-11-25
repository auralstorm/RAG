import { useEffect, useRef, useState } from 'react';
import { Alert, Button, Form, Input } from 'antd';
import type { SessionCredentials } from '@enterprise-rag/shared';

export function CredentialForm({
  onLogin,
  accountLabel,
}: {
  readonly onLogin?:
    | ((credentials: SessionCredentials, signal: AbortSignal) => Promise<void>)
    | undefined;
  readonly accountLabel: string;
}) {
  const [form] = Form.useForm<SessionCredentials>();
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
  async function submit(values: SessionCredentials) {
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
  return (
    <>
      {hasError ? (
        <Alert
          showIcon
          type="error"
          title="暂时无法登录，请检查账号密码后重试，或联系管理员。"
        />
      ) : null}
      <Form<SessionCredentials>
        form={form}
        name="account-login"
        layout="vertical"
        requiredMark={false}
        disabled={!onLogin || isSubmitting}
        clearOnDestroy
        onFinish={(values) => {
          void submit(values);
        }}
      >
        <Form.Item
          name="username"
          label={accountLabel}
          rules={[
            {
              required: true,
              whitespace: true,
              message: `请输入${accountLabel}。`,
            },
          ]}
        >
          <Input autoComplete="username" size="large" maxLength={128} />
        </Form.Item>
        <Form.Item
          name="password"
          label="密码"
          rules={[{ required: true, message: '请输入密码。' }]}
        >
          <Input.Password
            autoComplete="current-password"
            size="large"
            maxLength={1024}
          />
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
    </>
  );
}
