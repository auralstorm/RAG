import { Link, Navigate, Outlet } from 'react-router';
import {
  AccessScreen,
  SessionBoundary,
  SessionLogoutButton,
} from '@enterprise-rag/ui';

export function RequireSession() {
  return (
    <SessionBoundary
      loginFallback={<Navigate to="/login" replace />}
      recoveryAction={
        <>
          <SessionLogoutButton />
          <Link to="/login">返回登录</Link>
        </>
      }
    >
      <Outlet />
    </SessionBoundary>
  );
}

export function RouteErrorPage() {
  return (
    <AccessScreen
      title="页面暂时无法加载"
      description="请刷新页面重试，或返回登录页面。"
    >
      <a href="/login">返回登录</a>
    </AccessScreen>
  );
}
