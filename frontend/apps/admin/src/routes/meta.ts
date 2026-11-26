import type { ComponentType, LazyExoticComponent } from 'react';

export interface AppRouteMeta {
  path: string;
  name?: string;
  icon?: string;
  /** 权限标识，对应 access() 返回的 key */
  access?: string;
  /** false = 不套 ProLayout（对齐原 Umi 路由配置 layout: false） */
  layout?: boolean;
  redirect?: string;
  /** 懒加载页面组件 */
  lazy?: () => Promise<{ default: ComponentType }>;
  routes?: AppRouteMeta[];
}

/**
 * 精简版路由表，对齐原模板 config/routes.simple.ts
 * 由 scripts/simple.mjs 覆盖 src/routes/meta.ts 后删除本备份文件
 *
 * 精简后仅保留：登录、欢迎、二级管理页、查询表格、404
 */
export const routes: AppRouteMeta[] = [
  {
    path: '/user',
    layout: false,
    routes: [
      {
        path: '/user/login',
        name: 'login',
        lazy: () => import('@/pages/user/login'),
      },
    ],
  },
  {
    path: '/welcome',
    name: 'welcome',
    icon: 'home',
    lazy: () => import('@/pages/Welcome'),
  },
  {
    path: '/admin',
    name: 'admin',
    icon: 'crown',
    access: 'canAdmin',
    routes: [
      { path: '/admin', redirect: '/admin/sub-page' },
      {
        path: '/admin/sub-page',
        name: 'sub-page',
        lazy: () => import('@/pages/Admin'),
      },
    ],
  },
  {
    name: 'table-list',
    icon: 'table',
    path: '/list',
    lazy: () => import('@/pages/table-list'),
  },
  { path: '/', redirect: '/welcome' },
  { path: '/*', layout: false, lazy: () => import('@/pages/exception/404') },
];

export type { LazyExoticComponent };
