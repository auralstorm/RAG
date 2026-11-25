import { createContext, useContext } from 'react';
import type { ReactNode } from 'react';
import { Spin } from 'antd';
import { UNCONNECTED_SESSION } from '@enterprise-rag/shared';
import type { SessionState, SessionActions } from '@enterprise-rag/shared';
import { AccessScreen } from './AccessScreen';

const SessionContext = createContext<SessionState>(UNCONNECTED_SESSION);
const SessionActionsContext = createContext<SessionActions>({
  mode: 'unavailable',
});

export interface SessionStatusProps {
  readonly kind: 'checking' | 'error' | 'forbidden';
  readonly title: string;
  readonly description: string;
  readonly children: ReactNode;
}

export function SessionProvider({
  state,
  children,
  actions,
}: {
  readonly state: SessionState;
  readonly children: ReactNode;
  readonly actions?: SessionActions | undefined;
}) {
  return (
    <SessionActionsContext.Provider value={actions ?? { mode: 'unavailable' }}>
      <SessionContext.Provider value={state}>
        {children}
      </SessionContext.Provider>
    </SessionActionsContext.Provider>
  );
}

export function useSessionState() {
  return useContext(SessionContext);
}

export function useSessionActions() {
  return useContext(SessionActionsContext);
}

export function SessionBoundary({
  children,
  loginFallback,
  recoveryAction,
  requiredPermission,
  renderStatus,
}: {
  readonly children: ReactNode;
  readonly loginFallback: ReactNode;
  readonly recoveryAction: ReactNode;
  readonly requiredPermission?: string;
  readonly renderStatus?: (props: SessionStatusProps) => ReactNode;
}) {
  const state = useSessionState();
  if (state.status === 'anonymous') return loginFallback;
  if (
    state.status === 'authenticated' &&
    state.subjectId.trim() &&
    state.canAccessApplication &&
    state.authorization?.policyVersion &&
    Array.isArray(state.authorization.permissionCodes) &&
    (!requiredPermission ||
      state.authorization.permissionCodes.includes(requiredPermission))
  ) {
    return (
      <div key={`${state.subjectId}:${state.authorization.policyVersion}`}>
        {children}
      </div>
    );
  }
  if (state.status === 'checking') {
    const props: SessionStatusProps = {
      kind: 'checking',
      title: '正在确认登录状态',
      description: '请稍候。',
      children: (
        <div role="status">
          <Spin aria-label="正在确认登录状态" />
        </div>
      ),
    };
    return renderStatus ? renderStatus(props) : <AccessScreen {...props} />;
  }
  const props: SessionStatusProps = {
    kind: state.status === 'error' ? 'error' : 'forbidden',
    title: state.status === 'error' ? '暂时无法确认登录状态' : '暂无访问权限',
    description:
      state.status === 'error'
        ? '请刷新页面重试，或联系管理员。'
        : '请联系管理员确认账号和应用访问权限。',
    children: (
      <>
        {state.status === 'error' && state.requestId ? (
          <p>请求编号：{state.requestId}</p>
        ) : null}
        {recoveryAction}
      </>
    ),
  };
  return renderStatus ? renderStatus(props) : <AccessScreen {...props} />;
}
