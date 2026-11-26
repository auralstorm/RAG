import {
  Alert,
  Button,
  Empty,
  Popconfirm,
  Result,
  Space,
  Tag,
  Typography,
} from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import { ProTable, type ProColumns } from '@ant-design/pro-components/table';
import type { ProviderAdminView } from '@enterprise-rag/api-client';
import { ProviderEditor } from './ProviderEditor';
import { useProviderManagement } from './useProviderManagement';
import styles from './provider.module.css';

interface ProviderSearch {
  readonly name?: string;
  readonly provider_type?: string;
  readonly status?: 'ACTIVE' | 'DISABLED';
}

export function ProviderManagement() {
  const management = useProviderManagement();
  const { state, query, canManage, busy, editor } = management;
  const columns: ProColumns<ProviderAdminView>[] = [
    {
      title: '供应商名称',
      dataIndex: 'name',
      width: 180,
      fieldProps: { maxLength: 128 },
    },
    {
      title: '类型',
      dataIndex: 'provider_type',
      width: 160,
      fieldProps: { maxLength: 64 },
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 100,
      valueType: 'select',
      valueEnum: {
        ACTIVE: { text: '启用', status: 'Success' },
        DISABLED: { text: '停用', status: 'Default' },
      },
    },
    {
      title: '服务地址',
      dataIndex: 'base_url',
      search: false,
      width: 260,
      ellipsis: true,
      render: (_, provider) => (
        <Typography.Text ellipsis={{ tooltip: provider.base_url }}>
          {provider.base_url}
        </Typography.Text>
      ),
    },
    {
      title: 'API Key',
      dataIndex: 'has_credential',
      search: false,
      width: 110,
      render: (_, provider) =>
        provider.has_credential ? (
          <Tag color="success">已配置</Tag>
        ) : (
          <Tag>未配置</Tag>
        ),
    },
    {
      title: '代理',
      dataIndex: 'proxy_configured',
      search: false,
      width: 100,
      render: (_, provider) =>
        provider.proxy_configured ? (
          <Tag color="processing">已配置</Tag>
        ) : (
          <Tag>未配置</Tag>
        ),
    },
    {
      title: '超时（秒）',
      dataIndex: 'timeout_seconds',
      search: false,
      width: 110,
      align: 'right',
    },
    {
      title: '备注',
      dataIndex: 'remarks',
      search: false,
      ellipsis: true,
      width: 180,
    },
    {
      title: '更新时间',
      dataIndex: 'updated_at',
      search: false,
      valueType: 'dateTime',
      width: 180,
    },
    ...(canManage
      ? [
          {
            title: '操作',
            key: 'action',
            search: false,
            width: 200,
            render: (_: unknown, provider: ProviderAdminView) => (
              <Space size={0} wrap>
                <Button
                  type="link"
                  disabled={busy}
                  onClick={() => management.openEditor(provider)}
                >
                  编辑
                </Button>
                <Popconfirm
                  title={
                    provider.status === 'ACTIVE'
                      ? '停用此供应商？'
                      : '启用此供应商？'
                  }
                  description="状态变更会影响后续调用。"
                  okText="确认"
                  cancelText="取消"
                  disabled={busy}
                  onConfirm={() => management.changeStatus(provider)}
                >
                  <Button type="link" disabled={busy}>
                    {provider.status === 'ACTIVE' ? '停用' : '启用'}
                  </Button>
                </Popconfirm>
                <Popconfirm
                  title="删除此供应商？"
                  description="删除后将停用并从列表移除，历史配置仍会保留。"
                  okText="删除"
                  cancelText="取消"
                  okButtonProps={{ danger: true }}
                  disabled={busy}
                  onConfirm={() => management.remove(provider)}
                >
                  <Button type="link" danger disabled={busy}>
                    删除
                  </Button>
                </Popconfirm>
              </Space>
            ),
          },
        ]
      : []),
  ];

  if (management.accessDenied)
    return (
      <Result
        status="403"
        title={management.accessDenied === 401 ? '登录已过期' : '暂无访问权限'}
        subTitle="请重新确认登录状态和供应商管理权限。"
        extra={
          <Button onClick={() => window.location.reload()}>重新确认登录</Button>
        }
      />
    );

  return (
    <>
      {management.notice ? (
        <Alert
          className={styles.alert ?? ''}
          showIcon
          type={management.notice.type}
          title={management.notice.text}
        />
      ) : null}
      {state.status === 'error' ? (
        <Alert
          className={styles.alert ?? ''}
          type="error"
          showIcon
          title="供应商列表暂时无法加载。"
          description={
            state.requestId
              ? `请求编号：${state.requestId}`
              : '请检查服务连接后重试。'
          }
          action={<Button onClick={management.refresh}>重试</Button>}
        />
      ) : null}
      <ProTable<ProviderAdminView, ProviderSearch>
        rowKey="id"
        headerTitle="供应商列表"
        columns={columns}
        dataSource={state.items}
        loading={state.status === 'loading'}
        manualRequest
        scroll={{ x: 1600 }}
        search={{
          labelWidth: 'auto',
          defaultCollapsed: false,
          collapseRender: false,
        }}
        options={{
          density: true,
          setting: true,
          reload: () => management.refresh(),
        }}
        onSubmit={(values) => {
          management.setQuery((current) => ({
            page: 1,
            page_size: current.page_size,
            ...(values.name?.trim() ? { name: values.name.trim() } : {}),
            ...(values.provider_type?.trim()
              ? { provider_type: values.provider_type.trim() }
              : {}),
            ...(values.status ? { status: values.status } : {}),
          }));
          management.refresh();
        }}
        onReset={() => {
          management.setQuery((current) => ({
            page: 1,
            page_size: current.page_size,
          }));
          management.refresh();
        }}
        toolBarRender={() =>
          canManage
            ? [
                <Button
                  key="create"
                  type="primary"
                  icon={<PlusOutlined aria-hidden="true" />}
                  disabled={busy}
                  onClick={() => management.openEditor()}
                >
                  新建供应商
                </Button>,
              ]
            : []
        }
        pagination={{
          current: query.page,
          pageSize: query.page_size,
          total: state.total,
          showSizeChanger: true,
          pageSizeOptions: [10, 20, 50, 100],
          showTotal: (total) => `共 ${total} 个供应商`,
          onChange: (page, pageSize) =>
            management.setQuery((current) => ({
              ...current,
              page,
              page_size: pageSize,
            })),
        }}
        locale={{
          emptyText: (
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description={
                state.status === 'error' ? '列表加载失败。' : '暂无供应商配置。'
              }
            />
          ),
        }}
      />
      {editor ? (
        <ProviderEditor
          key={editor.provider?.id ?? 'create'}
          provider={editor.provider}
          busy={busy}
          onSave={management.save}
          onClose={management.closeEditor}
        />
      ) : null}
    </>
  );
}
