import {
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  ReadOutlined,
} from '@ant-design/icons';
import { ProLayout } from '@ant-design/pro-components/layout';
import { Button } from 'antd';
import { useState } from 'react';
import { Link, Outlet, useLocation, useNavigate } from 'react-router';

import { ADMIN_PAGES } from '@admin/routes/admin-pages';
import { SessionLogoutButton, useSessionState } from '@enterprise-rag/ui';

import styles from './admin.module.css';

export function AdminLayout() {
  const location = useLocation();
  const navigate = useNavigate();
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
        logo={<ReadOutlined aria-hidden />}
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
        onMenuHeaderClick={() => navigate('/admin')}
        collapsedButtonRender={(isCollapsed) => (
          <Button
            type="text"
            aria-label={isCollapsed ? '展开导航' : '收起导航'}
            aria-expanded={!isCollapsed}
            aria-controls="admin-navigation"
            icon={isCollapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
            onClick={() => setCollapsed(!isCollapsed)}
          />
        )}
        actionsRender={(props) =>
          [
            !props.isMobile && (
              <span key="internal" className={styles.internal}>
                企业内部
              </span>
            ),
            <SessionLogoutButton key="logout" />,
          ].filter(Boolean)
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
