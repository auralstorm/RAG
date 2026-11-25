export type { SessionState } from './session';
export { UNCONNECTED_SESSION } from './session';

export type ApplicationId = 'chat' | 'admin';

export const applicationLabels: Readonly<Record<ApplicationId, string>> = {
  chat: '企业知识助手',
  admin: '企业知识管理',
};
