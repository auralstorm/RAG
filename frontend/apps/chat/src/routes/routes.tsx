import { Link, Navigate } from 'react-router';
import type { RouteObject } from 'react-router';
import { AccessScreen } from '@enterprise-rag/ui';
import { RequireSession, RouteErrorPage } from './RouteBoundary';
import { LoginPage } from '@chat/pages/auth/LoginPage';

export function createChatRoutes(): RouteObject[] {
  const workspace = async () => {
    const { ChatWorkspacePage } =
      await import('@chat/pages/chat/ChatWorkspacePage');
    return { Component: ChatWorkspacePage };
  };
  return [
    {
      path: '/',
      errorElement: <RouteErrorPage />,
      hydrateFallbackElement: (
        <AccessScreen title="正在加载页面" description="请稍候。" />
      ),
      children: [
        { index: true, element: <Navigate to="/chat" replace /> },
        { path: 'login', element: <LoginPage /> },
        {
          element: <RequireSession />,
          children: [{ path: 'chat', lazy: workspace }],
        },
        ...(import.meta.env.DEV && import.meta.env.MODE === 'development'
          ? [
              {
                path: 'preview',
                lazy: async () => {
                  const { ChatWorkspacePage } =
                    await import('@chat/pages/chat/ChatWorkspacePage');
                  return { element: <ChatWorkspacePage isPreview /> };
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
