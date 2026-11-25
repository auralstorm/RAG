import { createElement } from 'react';
import { DashboardOutlined } from '@ant-design/icons';

export const DASHBOARD_PAGE = {
  path: '/admin',
  name: '服务概览',
  title: '企业知识管理',
  description: '统一配置模型、管理知识库与查看运行记录。',
  requiredPermission: 'dashboard.read',
  icon: createElement(DashboardOutlined, { 'aria-hidden': true }),
} as const;
