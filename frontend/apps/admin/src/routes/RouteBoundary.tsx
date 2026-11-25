import { Link, Navigate, Outlet } from 'react-router';
import { SessionBoundary, SessionLogoutButton } from '@enterprise-rag/ui';
import { AdminSessionStatus } from '@admin/app/AdminStatusScreen';

export function RequireSession({
  requiredPermission,
}: {
  readonly requiredPermission: string;
}) {
  return (
    <SessionBoundary
      loginFallback={<Navigate to="/login" replace />}
      recoveryAction={
        <>
          <SessionLogoutButton />
          <Link to="/login">返回登录</Link>
        </>
      }
      requiredPermission={requiredPermission}
      renderStatus={(props) => <AdminSessionStatus {...props} />}
    >
      <Outlet />
    </SessionBoundary>
  );
}
