import {
  LogoutOutlined,
  SettingOutlined,
  SkinOutlined,
} from '@ant-design/icons';
import type { MenuProps } from 'antd';
import { Spin } from 'antd';
import type React from 'react';
import { startTransition } from 'react';
import { useNavigate } from 'react-router';

import HeaderDropdown from '../HeaderDropdown';

import { outLogin } from '@/services/ant-design-pro/api';
import { useInitialStateStore } from '@/stores/initialState';


type GlobalHeaderRightProps = {
  children?: React.ReactNode;
};

const menuItems: MenuProps['items'] = [
  {
    key: 'settings',
    icon: <SettingOutlined />,
    label: '个人设置',
  },
  {
    key: 'theme',
    icon: <SkinOutlined />,
    label: '主题设置',
  },
  {
    type: 'divider' as const,
  },
  {
    key: 'logout',
    icon: <LogoutOutlined />,
    label: '退出登录',
  },
];

export const AvatarDropdown: React.FC<GlobalHeaderRightProps> = ({
  children,
}) => {
  const navigate = useNavigate();
  const currentUser = useInitialStateStore((s) => s.currentUser);
  const setInitialState = useInitialStateStore((s) => s.setInitialState);

  const loginOut = async () => {
    try {
      await outLogin();
    } catch {
      // Local logout has already cleared user state; redirect should still proceed.
    }
    const { search, pathname } = window.location;
    const urlParams = new URL(window.location.href).searchParams;
    const searchParams = new URLSearchParams({
      redirect: pathname + search,
    });
    const redirect = urlParams.get('redirect');
    if (window.location.pathname !== '/user/login' && !redirect) {
      navigate({ pathname: '/user/login', search: searchParams.toString() });
    }
  };

  const onMenuClick: MenuProps['onClick'] = (event) => {
    const { key } = event;
    if (key === 'logout') {
      startTransition(() => {
        setInitialState((s) => ({ ...s, currentUser: undefined }));
      });
      loginOut();
      return;
    }
    if (key === 'theme') {
      setInitialState((s) => ({ ...s, settingDrawerOpen: true }));
      return;
    }
    navigate(`/account/${key}`);
  };

  if (!currentUser) {
    return <Spin size="small" />;
  }

  return (
    <HeaderDropdown
      placement="bottomRight"
      menu={{
        selectedKeys: [],
        onClick: onMenuClick,
        items: menuItems,
      }}
      arrow
    >
      {children}
    </HeaderDropdown>
  );
};
