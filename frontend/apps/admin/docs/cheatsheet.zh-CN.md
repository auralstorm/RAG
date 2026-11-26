# Ant Design Pro Cheatsheet

> 本工程为 Ant Design Pro 6.0.3 的去 Umi 复刻版本：**Vite 7 + React Router 7 + Zustand + react-i18next**，UI 层沿用 antd 6 与 @ant-design/pro-components 3。

## 技术栈

- **React** 19 + **antd** 6 + **@ant-design/pro-components** 3
- **构建**：Vite 7（esbuild / Rollup）
- **路由**：react-router-dom 7（createBrowserRouter）
- **全局状态**：Zustand
- **服务端状态**：@tanstack/react-query 5
- **国际化**：i18next + react-i18next
- **请求**：axios 自建封装
- **样式**：Tailwind CSS v4 + antd-style + Less（全局遗留）
- **Mock**：Vite 中间件（`vite-plugins/mockPlugin.ts`）

## 快速开始

```bash
npm install      # 安装依赖
npm run dev      # 启动开发服务器（默认端口 8000，带 Mock）
npm run build    # 类型检查（tsc --noEmit）+ 生产构建，产物输出 dist/
npm run preview  # 本地预览已构建产物
```

环境要求：Node.js ≥ 20。

**目录结构：**

```
├── config/              # 布局主题默认配置
│   └── defaultSettings.ts
├── mock/                # 全局 Mock 数据
├── public/              # 静态资源（favicon、首屏 loading 脚本）
├── docs/                # 项目文档（本速查手册）
├── vite-plugins/
│   └── mockPlugin.ts    # Vite dev Mock 中间件
├── vite.config.ts       # Vite 配置（别名、define、Less、Mock 插件）
├── src/
│   ├── components/      # 公共组件（Footer、RightContent、SelectLang 等）
│   ├── layouts/         # AppLayout：ProLayout 包裹 + 鉴权守卫
│   ├── locales/         # 国际化资源（8 个语言）
│   ├── pages/           # 页面组件（含页面级 _mock.ts）
│   ├── routes/          # 路由元信息、路由表、菜单数据、图标映射
│   ├── services/        # API 服务层
│   ├── stores/          # Zustand 全局状态
│   ├── i18n/            # i18next 初始化与 umi 兼容层
│   ├── utils/           # request、format、chinaDivision 等工具
│   ├── access.ts        # 权限定义
│   └── main.tsx         # 应用入口
└── tailwind.css
```

**路径别名：**

| 别名 | 指向 |
|------|------|
| `@/*` | `./src/*` |
| `@root/*` | `./`（工程根目录） |

## 路由与菜单

**路由元信息** 位于 `src/routes/meta.ts`，与原模板路由表 1:1 对应：

```ts
// File: src/routes/meta.ts
export const routes: AppRouteMeta[] = [
  {
    path: '/welcome',
    name: 'welcome',      // 对应 menu.welcome 国际化 key
    icon: 'home',
    lazy: () => import('@/pages/Welcome'),
  },
  {
    path: '/admin',
    name: 'admin',
    icon: 'crown',
    access: 'canAdmin',  // 路由级权限控制
    routes: [...],
  },
  { path: '/', redirect: '/dashboard/analysis' },
];
```

**路由表** 在 `src/routes/index.tsx` 用 `createBrowserRouter` 组装：`layout: false` 的路由平铺，其余统一挂到 `AppLayout` 父路由下。菜单树由 `src/routes/menuData.ts` 根据路由元信息 + 权限过滤生成，字符串图标经 `src/routes/iconMap.tsx` 映射为 `@ant-design/icons` 组件。

**路由导航（React Router 7）：**

```tsx
import { Link, useNavigate, useLocation, useSearchParams } from 'react-router-dom';

const navigate = useNavigate();
navigate('/dashboard');   // 跳转
navigate(-1);            // 后退

const location = useLocation();          // 当前路由信息
const [searchParams] = useSearchParams(); // 查询参数
```

> 💡 `name` 字段自动映射为 `menu.xxx` 国际化 key，在 `src/locales/` 中配置翻译。

## 布局

**主题默认配置** 位于 `config/defaultSettings.ts`：

```ts
export default {
  navTheme: 'light',        // 导航主题：light / realDark
  colorPrimary: '#1677ff',  // 主题色
  layout: 'mix',             // 布局模式：side / top / mix
  contentWidth: 'Fluid',     // 内容宽度：Fluid / Fixed
  fixedHeader: false,        // 固定顶部导航
  fixSiderbar: true,         // 固定侧边栏
  title: 'Ant Design Pro',
};
```

**布局外壳** 在 `src/layouts/AppLayout.tsx`：用 `ProLayout` 包裹 `<Outlet />`，内含鉴权守卫、顶栏 `RightContent`、底部 `Footer` 与右侧 `SettingDrawer`。

**页面容器：**

```tsx
import { PageContainer } from '@ant-design/pro-components';

const Page = () => (
  <PageContainer header={{ title: '页面标题' }} content="页面描述">
    {/* 页面内容 */}
  </PageContainer>
);
```

**自定义区域：** 右上角 `src/components/RightContent`，底部 `src/components/Footer`。

## 全局状态

**初始状态（Zustand）** 位于 `src/stores/initialState.ts`，对应原模板的 `getInitialState`：

```ts
// 组件中读取
import { useInitialStateStore } from '@/stores/initialState';

const settings = useInitialStateStore((s) => s.settings);
const currentUser = useInitialStateStore((s) => s.currentUser);
```

应用启动时 `bootstrapInitialState()`（在 `src/main.tsx` 中调用）按当前路由决定是否拉取当前用户，结果写入同一 store。

**服务端状态（React Query）：**

```tsx
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';

const { data, isLoading } = useQuery({
  queryKey: ['user', id],
  queryFn: () => getUser(id),
});

const queryClient = useQueryClient();
const mutation = useMutation({
  mutationFn: updateUser,
  onSuccess: () => queryClient.invalidateQueries({ queryKey: ['user'] }),
});
```

> 💡 全局 `QueryClient` 在 `src/main.tsx` 的 `QueryClientProvider` 中创建。

## 请求

**请求封装** 位于 `src/utils/request.ts`，基于 axios 实例：

```ts
import { request } from '@/utils/request';

// GET
const data = await request<{ data: API.CurrentUser }>('/api/currentUser');

// POST
await request('/api/users', { method: 'POST', data: { name: 'test' } });
```

- 响应拦截器返回响应体 JSON；业务错误（响应体 `success === false`）抛出 `BizError`。
- 错误分级处理在 `src/requestErrorConfig.ts`（message / notification）。
- 开发环境 `baseURL` 为空（走本地 Mock）；生产环境指向远程演示 API。

**服务层写法** 见 `src/services/ant-design-pro/`，每个接口一个异步函数，内部调用 `request`。

## 权限

**定义权限** 在 `src/access.ts`：

```ts
export default function access(initialState: { currentUser?: API.CurrentUser } | undefined) {
  const { currentUser } = initialState ?? {};
  return {
    canAdmin: currentUser && currentUser.access === 'admin',
  };
}
```

**路由级权限：** 路由元信息中添加 `access` 字段，`AppLayout` 据此过滤菜单与可访问路由。

**组件级判断：** 在组件中读取权限集合（由 `access({ currentUser })` 生成）后按条件渲染。

## 国际化

**初始化** 在 `src/i18n/index.ts`，默认语言 `zh-CN`，内置 8 个语言：`zh-CN`、`zh-TW`、`en-US`、`ja-JP`、`pt-BR`、`id-ID`、`fa-IR`、`bn-BD`。

**文件结构：**

```
src/locales/
├── zh-CN.ts        # 中文入口（聚合分片）
├── zh-CN/
│   ├── menu.ts     # 菜单翻译
│   ├── pages.ts    # 页面翻译
│   └── ...
├── en-US.ts
└── en-US/
    └── ...
```

**使用方式（兼容层 `src/i18n/intl.tsx`）：**

```tsx
import { useIntl, FormattedMessage } from '@/i18n/intl';

// Hook 方式
const intl = useIntl();
intl.formatMessage({ id: 'menu.welcome' });

// 组件方式
<FormattedMessage id="menu.welcome" />
```

**切换语言：**

```tsx
import { setLocale, getLocale, getAllLocales } from '@/i18n/intl';

setLocale('en-US');   // 切换语言，偏好持久化到 localStorage
const lang = getLocale();
```

> 💡 语言偏好存储键为 `antd_pro_locale`。

## 样式

**Tailwind CSS v4：** 直接在 className 中使用：

```tsx
<div className="flex items-center gap-4 p-6 rounded-lg bg-white" />
```

**antd-style（CSS-in-JS）：**

```tsx
import { createStyles } from 'antd-style';

const useStyles = createStyles(({ token, css }) => ({
  card: css`
    background: ${token.colorBgContainer};
    border-radius: ${token.borderRadiusLG}px;
  `,
}));

const { styles } = useStyles();
<div className={styles.card} />;
```

**Less / 全局样式：** 全局样式在 `src/global.less`，`src/global.style.ts` 通过 antd-style 注入全局 token 样式。

**动态主题：** 开发环境可通过右下角 `SettingDrawer` 实时切换导航主题、主题色等。

> 💡 三种方案可共存：Tailwind 适合布局、antd-style 适合消费主题 token、Less 仅用于遗留全局样式。

## Mock

**Mock 中间件** 位于 `vite-plugins/mockPlugin.ts`，作为 Vite dev server 中间件拦截 `/api/**` 请求：

- **全局 Mock**：`mock/` 目录下的 `.ts` 文件。
- **页面级 Mock**：`src/pages/**/_mock.ts`，与页面同目录。

**Mock 格式（express 风格 req / res）：**

```ts
// File: mock/user.ts
import type { Request, Response } from 'express';

export default {
  'GET /api/currentUser': (_req: Request, res: Response) => {
    res.json({ name: 'Serati Ma', access: 'admin' });
  },
  'POST /api/login': async (req: Request, res: Response) => {
    res.json({ status: 'ok' });
  },
};
```

- key 格式为 `METHOD /path`，省略 method 时匹配全部方法；路径参数用 `:param` 声明。
- 处理器可为函数，也可直接返回对象 / 数组作为响应体。

## 常见任务

### 添加新页面

```bash
# 1. 创建页面组件
#    src/pages/my-page/index.tsx

# 2. 在路由元信息注册
#    src/routes/meta.ts
#    { path: '/my-page', name: 'myPage', icon: 'file', lazy: () => import('@/pages/my-page') }

# 3. 添加菜单国际化（如需菜单显示）
#    src/locales/zh-CN/menu.ts  → menu.myPage: '我的页面'
#    src/locales/en-US/menu.ts  → menu.myPage: 'My Page'
```

### 添加全局状态

在 `src/stores/` 下用 Zustand `create` 定义 store，组件中通过 selector 读取；跨页面共享的初始用户信息、主题设置统一收敛到 `initialState` store。

### 添加 Mock 接口

```bash
# 全局 Mock：mock/api.ts
# 页面级 Mock：src/pages/my-page/_mock.ts

# 格式：
# export default { 'GET /api/my-data': { data: [] } }
```

## 注意事项

- **路径别名**：`@/*` → `./src/*`，`@root/*` → `./`。
- **类型检查**：`npm run build` 已包含 `tsc --noEmit`，不产出 `.js` 到源码目录；也可单独执行 `./node_modules/.bin/tsc --noEmit`。
- **无 Umi 运行时**：本工程不依赖 `@umijs/max`，路由、状态、请求、国际化、权限、Mock 均由上述自建模块实现。
- **样式优先级**：Tailwind（布局）> antd-style（主题 token）> 组件局部样式 > Less（仅遗留全局）。
- **Commit 规范**：遵循 [Conventional Commits](https://www.conventionalcommits.org/)，如 `feat:`、`fix:`、`chore:`、`refactor:`。
