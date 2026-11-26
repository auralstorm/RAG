/**
 * 权限定义：对应原 Umi access 插件
 * access(currentUser) => 权限集合
 */
export default function access(
  initialState:
    | {
        currentUser?: API.CurrentUser;
      }
    | undefined,
) {
  const { currentUser } = initialState ?? {};
  return {
    canAdmin: currentUser && currentUser.access === 'admin',
  };
}
