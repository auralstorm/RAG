import { PageContainer } from '@ant-design/pro-components/layout';

import layoutStyles from '@admin/layouts/admin.module.css';
import { PROVIDER_PAGE, ProviderManagement } from '@admin/modules/modelGateway';

export function ProviderPage() {
  return (
    <PageContainer
      title={<h1 className={layoutStyles.pageTitle}>{PROVIDER_PAGE.title}</h1>}
      content={PROVIDER_PAGE.description}
      breadcrumbRender={(_, dom) => (
        <div role="group" aria-label="页面位置">
          {dom}
        </div>
      )}
      breadcrumb={{
        items: [{ title: '管理工作台' }, { title: PROVIDER_PAGE.name }],
      }}
    >
      <ProviderManagement />
    </PageContainer>
  );
}
