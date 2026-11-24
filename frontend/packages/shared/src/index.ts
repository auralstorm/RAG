export type ApplicationId = 'chat' | 'admin';

export const applicationLabels: Readonly<Record<ApplicationId, string>> = {
  chat: '企业知识助手',
  admin: '企业知识管理',
};
