import { useState } from 'react';
import { Link, Outlet, useLocation } from 'react-router';
import { MenuFoldOutlined, MenuUnfoldOutlined } from '@ant-design/icons';
import { ProLayout } from '@ant-design/pro-components/layout';
import { Button } from 'antd';
import { SessionLogoutButton, useSessionState } from '@enterprise-rag/ui';
import { ADMIN_PAGES } from '@admin/routes/admin-pages';
import { EnterpriseBrand } from './EnterpriseBrand';
import styles from './admin.module.css';

export function AdminLayout() {
  const location = useLocation();
  const session = useSessionState();
  const [collapsed, setCollapsed] = useState(false);
  const pages = ADMIN_PAGES.filter(
    (page) =>
      session.status === 'authenticated' &&
      session.authorization.permissionCodes.includes(page.requiredPermission),
  );
  return (
    <div className={styles.workspace}>
      <a href="#admin-content" className={styles.skip}>
        跳至页面内容
      </a>
      <ProLayout
        title="EnterpriseRag"
        logo={false}
        layout="mix"
        navTheme="light"
        contentWidth="Fluid"
        fixedHeader
        fixSiderbar
        siderWidth={224}
        token={{
          header: { heightLayoutHeader: 64 },
          pageContainer: { paddingInlinePageContainerContent: 24 },
        }}
        locale="zh-CN"
        menu={{ locale: false }}
        location={{ pathname: location.pathname }}
        route={{
          path: '/',
          routes: pages.map((page) => ({
            path: page.path,
            name: page.name,
            icon: page.icon,
          })),
        }}
        collapsed={collapsed}
        onCollapse={setCollapsed}
        collapsedButtonRender={false}
        headerRender={(props) => (
          <div className={styles.header}>
            <Button
              type="text"
              aria-label={collapsed ? '展开导航' : '收起导航'}
              aria-expanded={!collapsed}
              aria-controls="admin-navigation"
              icon={collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
              onClick={() => setCollapsed(!collapsed)}
            />
            <EnterpriseBrand />
            <span className={styles.headerLabel}>管理工作台</span>
            <div className={styles.headerActions}>
              <SessionLogoutButton />
            </div>
            {props.isMobile ? null : (
              <span className={styles.internal}>企业内部</span>
            )}
          </div>
        )}
        menuHeaderRender={(_, __, props) =>
          props?.isMobile ? <EnterpriseBrand /> : null
        }
        menuExtraRender={(props) =>
          props.isMobile ? (
            <Button onClick={() => setCollapsed(true)}>关闭导航</Button>
          ) : null
        }
        menuContentRender={(_, dom) => (
          <nav id="admin-navigation" aria-label="管理导航">
            {dom}
          </nav>
        )}
        menuItemRender={(item, dom) =>
          item.path ? (
            <Link
              to={item.path}
              aria-current={
                location.pathname === item.path ? 'page' : undefined
              }
              onClick={() => {
                if (window.matchMedia('(max-width: 767px)').matches)
                  setCollapsed(true);
              }}
            >
              {dom}
            </Link>
          ) : (
            dom
          )
        }
        contentStyle={{ minWidth: 0, padding: 0 }}
        footerRender={false}
      >
        <div id="admin-content" className={styles.content} tabIndex={-1}>
          <Outlet />
        </div>
      </ProLayout>
    </div>
  );
}
