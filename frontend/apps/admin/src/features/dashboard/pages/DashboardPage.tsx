import { Alert, Button, Empty, Table, theme } from 'antd';
import type { TableColumnsType } from 'antd';
import { applicationLabels } from '@enterprise-rag/shared';
import { ApplicationShell, SessionLogoutButton } from '@enterprise-rag/ui';
import { useApiConnection } from '../hooks/use-api-connection';
import styles from './DashboardPage.module.css';

interface ServiceRow {
  readonly id: string;
  readonly name: string;
  readonly status: string;
}

const COLUMNS: TableColumnsType<ServiceRow> = [
  { title: '服务', dataIndex: 'name', rowScope: 'row' },
  { title: '连接状态', dataIndex: 'status' },
];
const CONNECTED_SERVICES: ServiceRow[] = [
  { id: 'api', name: '后端 API', status: '可连接' },
];

export function DashboardPage({
  isPreview = false,
}: {
  readonly isPreview?: boolean;
}) {
  const { token } = theme.useToken();
  const { state, checkConnection } = useApiConnection();
  const isLoading = state.status === 'loading';
  return (
    <ApplicationShell
      title={applicationLabels.admin}
      description="统一配置模型、管理知识库与查看运行记录。"
    >
      <section
        className={styles.connection}
        aria-labelledby="connection-heading"
        aria-busy={isLoading}
      >
        {isPreview ? (
          <Alert
            type="info"
            showIcon
            title="开发预览"
            description="仅检查公开 API 的连通性，不代表已登录或获得管理权限。"
          />
        ) : null}
        <div className={styles.toolbar}>
          <h2 id="connection-heading">服务连接</h2>
          <SessionLogoutButton />
          <Button
            aria-label={state.status === 'error' ? '重试连接' : '检查连接'}
            loading={isLoading}
            disabled={isLoading}
            onClick={() => {
              void checkConnection();
            }}
          >
            {state.status === 'error' ? '重试连接' : '检查连接'}
          </Button>
        </div>
        <p className={styles.description}>
          连接结果仅表示 API
          进程可以响应，不代表身份服务、知识问答或其他依赖已就绪。
        </p>
        <div role="status" aria-live="polite">
          {isLoading
            ? '正在检查服务连接…'
            : state.status === 'connected'
              ? '服务连接检查完成。'
              : null}
        </div>
        {state.status === 'error' ? (
          <Alert
            type="error"
            showIcon
            title="暂时无法连接服务，请重试。"
            description={
              state.requestId ? `请求编号：${state.requestId}` : undefined
            }
          />
        ) : null}
        <Table<ServiceRow>
          rowKey="id"
          columns={COLUMNS}
          dataSource={state.status === 'connected' ? CONNECTED_SERVICES : []}
          pagination={false}
          loading={isLoading}
          locale={{
            emptyText: (
              <Empty
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                styles={{ description: { color: token.colorTextSecondary } }}
                description={
                  state.status === 'idle'
                    ? '尚未检查服务连接，请点击“检查连接”。'
                    : isLoading
                      ? '正在等待检查结果。'
                      : '暂无可用的连接结果。'
                }
              />
            ),
          }}
        />
      </section>
    </ApplicationShell>
  );
}
