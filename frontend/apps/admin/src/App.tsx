import { applicationLabels } from '@enterprise-rag/shared';
import { ApplicationShell } from '@enterprise-rag/ui';

export function App() {
  return (
    <ApplicationShell
      title={applicationLabels.admin}
      description="统一配置模型、管理知识库与查看运行记录。"
    >
      <p>知识管理功能即将开放。</p>
    </ApplicationShell>
  );
}
