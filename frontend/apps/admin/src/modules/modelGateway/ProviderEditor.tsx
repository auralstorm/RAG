import { Alert, Checkbox, Form, Input, InputNumber, Modal } from 'antd';
import type { ProviderAdminView } from '@enterprise-rag/api-client';
import type { ProviderFormValues } from './useProviderManagement';
import styles from './provider.module.css';

export function ProviderEditor({
  provider,
  busy,
  onSave,
  onClose,
}: {
  readonly provider?: ProviderAdminView | undefined;
  readonly busy: boolean;
  readonly onSave: (values: ProviderFormValues) => Promise<void> | undefined;
  readonly onClose: () => void;
}) {
  const [form] = Form.useForm<ProviderFormValues>();
  return (
    <Modal
      open
      centered
      styles={{
        body: { maxHeight: 'calc(100dvh - 180px)', overflowY: 'auto' },
      }}
      title={provider ? '编辑供应商' : '新建供应商'}
      onCancel={onClose}
      onOk={() => form.submit()}
      okText="确认保存"
      cancelText="取消"
      confirmLoading={busy}
      cancelButtonProps={{ disabled: busy }}
      closable={!busy}
      mask={{ closable: !busy }}
      width={640}
    >
      <Alert
        className={styles.editorAlert ?? ''}
        type="info"
        showIcon
        title="API Key 与代理地址仅供写入，保存后不再展示。编辑时留空保留原值。"
      />
      <Form<ProviderFormValues>
        form={form}
        layout="vertical"
        preserve={false}
        disabled={busy}
        initialValues={{
          ...provider,
          timeout_seconds: provider?.timeout_seconds ?? 120,
          clear_proxy: false,
          confirm: false,
        }}
        onFinish={(values) => {
          const operation = onSave(values);
          form.setFieldsValue({
            credential: undefined,
            proxy_url: undefined,
            confirm: false,
          });
          void operation;
        }}
      >
        <div className={styles.formGrid ?? ''}>
          <Form.Item
            name="name"
            label="供应商名称"
            rules={[
              {
                required: true,
                whitespace: true,
                message: '请输入供应商名称。',
              },
            ]}
          >
            <Input maxLength={128} />
          </Form.Item>
          <Form.Item
            name="provider_type"
            label="供应商类型"
            rules={[
              {
                required: true,
                pattern: /^[a-z][a-z0-9_]{0,63}$/,
                message: '请使用小写字母、数字或下划线，以字母开头。',
              },
            ]}
          >
            <Input maxLength={64} placeholder="例如 openai_compatible" />
          </Form.Item>
          <Form.Item
            name="base_url"
            label="服务地址"
            className={styles.fullWidth ?? ''}
            rules={[
              {
                required: true,
                type: 'url',
                message: '请输入有效的 HTTP 或 HTTPS 地址。',
              },
            ]}
          >
            <Input
              type="url"
              maxLength={2048}
              placeholder="https://api.example.com/v1"
            />
          </Form.Item>
          <Form.Item
            name="timeout_seconds"
            label="请求超时（秒）"
            rules={[
              {
                required: true,
                type: 'integer',
                min: 1,
                max: 300,
                message: '请输入 1 至 300 之间的整数。',
              },
            ]}
          >
            <InputNumber
              min={1}
              max={300}
              precision={0}
              className={styles.numberInput ?? ''}
            />
          </Form.Item>
          <Form.Item
            name="credential"
            label="API Key"
            className={styles.fullWidth ?? ''}
          >
            <Input.Password
              autoComplete="new-password"
              maxLength={4096}
              placeholder={
                provider ? '留空保留现有 Key' : '可选，后续调用前需配置'
              }
            />
          </Form.Item>
          <Form.Item
            name="proxy_url"
            label="HTTP(S) 代理地址"
            className={styles.fullWidth ?? ''}
          >
            <Input.Password
              autoComplete="new-password"
              maxLength={2048}
              placeholder="可选；留空保留现有代理"
            />
          </Form.Item>
          {provider?.proxy_configured ? (
            <Form.Item
              name="clear_proxy"
              valuePropName="checked"
              className={styles.fullWidth ?? ''}
            >
              <Checkbox>移除当前代理（请勿同时填写新代理）</Checkbox>
            </Form.Item>
          ) : null}
          <Form.Item
            name="remarks"
            label="备注"
            className={styles.fullWidth ?? ''}
          >
            <Input.TextArea
              maxLength={1000}
              showCount
              autoSize={{ minRows: 2, maxRows: 4 }}
              placeholder="用途说明，请勿填写密钥或密码"
            />
          </Form.Item>
          <Form.Item
            name="confirm"
            valuePropName="checked"
            className={styles.fullWidth ?? ''}
            rules={[
              {
                validator: (_, value: unknown) =>
                  value === true
                    ? Promise.resolve()
                    : Promise.reject(new Error('请确认后再保存。')),
              },
            ]}
          >
            <Checkbox>我确认保存此配置，后续调用将使用新的配置。</Checkbox>
          </Form.Item>
        </div>
      </Form>
    </Modal>
  );
}
