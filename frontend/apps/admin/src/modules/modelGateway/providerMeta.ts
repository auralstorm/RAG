import { ApiOutlined } from '@ant-design/icons';
import { createElement } from 'react';

export const PROVIDER_PAGE = {
  path: '/admin/providers',
  name: '模型供应商',
  title: '模型供应商',
  description: '管理模型服务地址、访问凭据和连接设置。',
  requiredPermission: 'provider.read',
  icon: createElement(ApiOutlined, { 'aria-hidden': true }),
} as const;
