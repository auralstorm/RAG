import { createContext, useContext } from 'react';
import type { ReactNode } from 'react';
import { Spin } from 'antd';
import { UNCONNECTED_SESSION } from '@enterprise-rag/shared';
import type { SessionState } from '@enterprise-rag/shared';
import { AccessScreen } from './AccessScreen';

const SessionContext = createContext<SessionState>(UNCONNECTED_SESSION);

export function SessionProvider({
  state,
  children,
}: {
  readonly state: SessionState;
  readonly children: ReactNode;
}) {
  return (
    <SessionContext.Provider value={state}>{children}</SessionContext.Provider>
  );
}

export function useSessionState() {
  return useContext(SessionContext);
}

export function SessionBoundary({
  children,
  loginFallback,
  recoveryAction,
}: {
  readonly children: ReactNode;
  readonly loginFallback: ReactNode;
  readonly recoveryAction: ReactNode;
}) {
  const state = useSessionState();
  if (state.status === 'anonymous') return loginFallback;
  if (
    state.status === 'authenticated' &&
    state.subjectId.trim() &&
    state.canAccessApplication
  ) {
    return <div key={state.subjectId}>{children}</div>;
  }
  if (state.status === 'checking') {
    return (
      <AccessScreen title="正在确认登录状态" description="请稍候。">
        <div role="status">
          <Spin aria-label="正在确认登录状态" />
        </div>
      </AccessScreen>
    );
  }
  return (
    <AccessScreen
      title={state.status === 'error' ? '暂时无法确认登录状态' : '暂无访问权限'}
      description={
        state.status === 'error'
          ? '请刷新页面重试，或联系管理员。'
          : '请联系管理员确认账号和应用访问权限。'
      }
    >
      {state.status === 'error' && state.requestId ? (
        <p>请求编号：{state.requestId}</p>
      ) : null}
      {recoveryAction}
    </AccessScreen>
  );
}
