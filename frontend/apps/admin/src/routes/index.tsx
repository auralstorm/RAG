import { lazy, Suspense, type ReactNode } from 'react';
import {
  createBrowserRouter,
  Navigate,
  type RouteObject,
} from 'react-router';

import { routes, type AppRouteMeta } from './meta';

import AppLayout from '@/layouts/AppLayout';
import Loading from '@/loading';


function renderElement(meta: AppRouteMeta): ReactNode {
  if (meta.redirect) {
    return <Navigate to={meta.redirect} replace />;
  }
  if (!meta.lazy) return null;
  const Comp = lazy(meta.lazy);
  return (
    <Suspense fallback={<Loading />}>
      <Comp />
    </Suspense>
  );
}

function toRoutes(meta: AppRouteMeta[]): RouteObject[] {
  return meta.map((item) => ({
    path: item.path,
    element: renderElement(item),
    children: item.routes ? toRoutes(item.routes) : undefined,
  }));
}

/**
 * 顶层拆分：layout:false 的路由平铺，其余统一挂到 AppLayout 下
 */
function splitTopLevel(meta: AppRouteMeta[]) {
  const bare: AppRouteMeta[] = [];
  const layout: AppRouteMeta[] = [];
  for (const item of meta) {
    (item.layout === false ? bare : layout).push(item);
  }
  return { bare, layout };
}

const { bare, layout } = splitTopLevel(routes);

export const router = createBrowserRouter([
  ...toRoutes(bare),
  {
    element: <AppLayout />,
    children: toRoutes(layout),
  },
]);
