import { applicationLabels } from '@enterprise-rag/shared';
import { ApplicationShell } from '@enterprise-rag/ui';

export function App() {
  return (
    <ApplicationShell
      title={applicationLabels.chat}
      description="集中查阅企业知识，获取可追溯的答案。"
    >
      <p>知识库问答即将开放。</p>
    </ApplicationShell>
  );
}
