import { Link, Navigate, Outlet } from 'react-router';
import { SessionBoundary, SessionLogoutButton } from '@enterprise-rag/ui';

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
      requiredPermission="dashboard.read"
    >
      <Outlet />
    </SessionBoundary>
  );
}
