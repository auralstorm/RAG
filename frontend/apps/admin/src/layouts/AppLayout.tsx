import { ProLayout, SettingDrawer } from '@ant-design/pro-components';
import type React from 'react';
import { useEffect, useMemo } from 'react';
import { Link, Outlet, useLocation, useNavigate } from 'react-router';

import access from '@/access';
import { AvatarDropdown, DocLink, Footer, VersionDropdown } from '@/components';
import { buildMenuData } from '@/routes/menuData';
import { routes } from '@/routes/meta';
import { useInitialStateStore } from '@/stores/initialState';

const loginPath = '/user/login';

const AppLayout: React.FC = () => {
  const location = useLocation();
  const navigate = useNavigate();

  const settings = useInitialStateStore((s) => s.settings);
  const currentUser = useInitialStateStore((s) => s.currentUser);
  const settingDrawerOpen = useInitialStateStore((s) => s.settingDrawerOpen);
  const setInitialState = useInitialStateStore((s) => s.setInitialState);

  // 鉴权守卫：未登录访问受保护页面时跳转登录页并携带 redirect
  useEffect(() => {
    if (!currentUser && location.pathname !== loginPath) {
      const redirect = encodeURIComponent(
        location.pathname + location.search + location.hash,
      );
      navigate(`${loginPath}?redirect=${redirect}`, { replace: true });
    }
  }, [currentUser, location, navigate]);

  const menuData = useMemo(() => {
    const accessMap = access({ currentUser }) as Record<string, boolean>;
    return buildMenuData(routes, accessMap);
  }, [currentUser]);

  const logo = (settings as { logo?: string }).logo;

  return (
    <ProLayout
      route={{ path: '/', children: menuData as unknown as never[] }}
      location={location}
      title={settings.title}
      logo={logo}
      siderWidth={256}
      menuItemRender={(item, dom) =>
        item.path ? <Link to={item.path}>{dom}</Link> : dom
      }
      actionsRender={() => [<DocLink key="doc" />, <VersionDropdown key="version" />]}
      avatarProps={{
        src: currentUser?.avatar,
        title: 'ProUser',
        render: (_, avatarChildren) => (
          <AvatarDropdown>{avatarChildren}</AvatarDropdown>
        ),
      }}
      footerRender={() => <Footer />}
      bgLayoutImgList={[
        {
          src: 'https://mdn.alipayobjects.com/yuyan_qk0oxh/afts/img/D2LWSqNny4sAAAAAAAAAAAAAFl94AQBr',
          left: 85,
          bottom: 100,
          height: '303px',
        },
        {
          src: 'https://mdn.alipayobjects.com/yuyan_qk0oxh/afts/img/C2TWRpJpiC0AAAAAAAAAAAAAFl94AQBr',
          bottom: -68,
          right: -45,
          height: '303px',
        },
        {
          src: 'https://mdn.alipayobjects.com/yuyan_qk0oxh/afts/img/F6vSTbj8KpYAAAAAAAAAAAAAFl94AQBr',
          bottom: 0,
          left: 0,
          width: '331px',
        },
      ]}
      {...settings}
    >
      <>
        <Outlet />
        <SettingDrawer
          disableUrlParams
          enableDarkTheme
          collapse={settingDrawerOpen}
          onCollapseChange={(open) => {
            setInitialState({ settingDrawerOpen: open });
          }}
          settings={settings}
          onSettingChange={(next) => {
            setInitialState({ settings: next });
          }}
        />
      </>
    </ProLayout>
  );
};

export default AppLayout;
