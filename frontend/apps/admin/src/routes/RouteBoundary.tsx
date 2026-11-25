import { Link, Navigate, Outlet } from 'react-router';
import { SessionBoundary } from '@enterprise-rag/ui';

export function RequireSession() {
  return (
    <SessionBoundary
      loginFallback={<Navigate to="/login" replace />}
      recoveryAction={<Link to="/login">返回登录</Link>}
    >
      <Outlet />
    </SessionBoundary>
  );
}
