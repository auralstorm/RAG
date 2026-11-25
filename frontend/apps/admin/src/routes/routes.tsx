import { Link, Navigate } from 'react-router';
import type { RouteObject } from 'react-router';
import { AccessScreen } from '@enterprise-rag/ui';
import { RequireSession } from './RouteBoundary';
import { LoginPage } from '../features/auth/pages/LoginPage';

export function createAdminRoutes(): RouteObject[] {
  return [
    {
      path: '/',
      errorElement: (
        <AccessScreen
          title="页面暂时无法加载"
          description="请刷新页面重试，或返回登录页面。"
        >
          <a href="/login">返回登录</a>
        </AccessScreen>
      ),
      hydrateFallbackElement: (
        <AccessScreen title="正在加载页面" description="请稍候。" />
      ),
      children: [
        { index: true, element: <Navigate to="/admin" replace /> },
        { path: 'login', element: <LoginPage /> },
        {
          element: <RequireSession />,
          children: [
            {
              path: 'admin',
              lazy: async () => {
                const { DashboardPage } =
                  await import('../features/dashboard/pages/DashboardPage');
                return { Component: DashboardPage };
              },
            },
          ],
        },
        ...(import.meta.env.DEV && import.meta.env.MODE === 'development'
          ? [
              {
                path: 'preview',
                lazy: async () => {
                  const { DashboardPage } =
                    await import('../features/dashboard/pages/DashboardPage');
                  return { element: <DashboardPage isPreview /> };
                },
              },
            ]
          : []),
        {
          path: '*',
          element: (
            <AccessScreen
              title="页面不存在"
              description="请检查地址，或返回登录页面。"
            >
              <Link to="/login">返回登录</Link>
            </AccessScreen>
          ),
        },
      ],
    },
  ];
}
