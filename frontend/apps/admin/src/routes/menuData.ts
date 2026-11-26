import type { MenuDataItem } from '@ant-design/pro-components';

import { resolveIcon } from './iconMap';
import type { AppRouteMeta } from './meta';

/**
 * 路由元信息 → ProLayout 菜单树
 * 过滤 redirect、layout:false 与无权限项
 */
export function buildMenuData(
  meta: AppRouteMeta[],
  accessMap: Record<string, boolean>,
): MenuDataItem[] {
  const result: MenuDataItem[] = [];
  for (const item of meta) {
    if (item.redirect) continue;
    if (item.layout === false) continue;
    if (item.access && !accessMap[item.access]) continue;

    const children = item.routes
      ? buildMenuData(item.routes, accessMap)
      : undefined;
    if (item.routes && children && children.length === 0) continue;

    result.push({
      path: item.path,
      name: item.name,
      icon: resolveIcon(item.icon),
      children,
    });
  }
  return result;
}
