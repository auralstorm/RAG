import { Button } from 'antd';
import { useSessionActions, useSessionState } from './SessionBoundary';

export function SessionLogoutButton() {
  const actions = useSessionActions();
  const state = useSessionState();
  if (!actions.logout || state.status !== 'authenticated') return null;
  return (
    <Button
      type="text"
      onClick={() => {
        void actions.logout?.();
      }}
    >
      退出登录
    </Button>
  );
}
