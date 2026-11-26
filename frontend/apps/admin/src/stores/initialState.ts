import type { Settings as LayoutSettings } from '@ant-design/pro-components';
import defaultSettings from '@root/config/defaultSettings';
import { create } from 'zustand';

import { currentUser as queryCurrentUser } from '@/services/ant-design-pro/api';

const loginPath = '/user/login';
const publicPaths = [loginPath, '/user/register', '/user/register-result'];

export interface InitialState {
  settings: Partial<LayoutSettings>;
  currentUser?: API.CurrentUser;
  loading: boolean;
  fetchUserInfo?: () => Promise<API.CurrentUser | undefined>;
  settingDrawerOpen: boolean;
  setInitialState: (
    patch:
      | Partial<Omit<InitialState, 'setInitialState'>>
      | ((s: InitialState) => Partial<Omit<InitialState, 'setInitialState'>>),
  ) => void;
}

async function fetchUserInfo(): Promise<API.CurrentUser | undefined> {
  try {
    const msg = await queryCurrentUser({ skipErrorHandler: true });
    return msg.data;
  } catch {
    const { pathname, search, hash } = window.location;
    const redirect = encodeURIComponent(pathname + search + hash);
    window.location.href = `${loginPath}?redirect=${redirect}`;
  }
  return undefined;
}

export const useInitialStateStore = create<InitialState>((set) => ({
  settings: defaultSettings as Partial<LayoutSettings>,
  currentUser: undefined,
  loading: false,
  fetchUserInfo,
  settingDrawerOpen: false,
  setInitialState: (patch) =>
    set((s) => ({
      ...s,
      ...(typeof patch === 'function' ? patch(s) : patch),
    })),
}));

/** 对应原 Umi getInitialState：应用启动时按当前路由决定是否拉取当前用户 */
export async function bootstrapInitialState() {
  const { pathname } = window.location;
  if (publicPaths.includes(pathname)) return;
  const currentUser = await useInitialStateStore.getState().fetchUserInfo?.();
  useInitialStateStore.setState({ currentUser });
}
