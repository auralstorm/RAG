# Ant Design Pro Cheatsheet

> This project is a Umi-free replica of Ant Design Pro 6.0.3: **Vite 7 + React Router 7 + Zustand + react-i18next**, keeping antd 6 and @ant-design/pro-components 3 on the UI layer.

## Tech Stack

- **React** 19 + **antd** 6 + **@ant-design/pro-components** 3
- **Build**: Vite 7 (esbuild / Rollup)
- **Routing**: react-router-dom 7 (`createBrowserRouter`)
- **Global state**: Zustand
- **Server state**: @tanstack/react-query 5
- **i18n**: i18next + react-i18next
- **Request**: self-built axios wrapper
- **Styles**: Tailwind CSS v4 + antd-style + Less (legacy global)
- **Mock**: Vite middleware (`vite-plugins/mockPlugin.ts`)

## Getting Started

```bash
npm install      # Install dependencies
npm run dev      # Start dev server (port 8000, with Mock)
npm run build    # Type check (tsc --noEmit) + production build to dist/
npm run preview  # Preview the built bundle locally
```

Requires Node.js ≥ 20.

**Directory structure:**

```
├── config/              # Layout theme defaults
│   └── defaultSettings.ts
├── mock/                # Global Mock data
├── public/              # Static assets (favicon, first-screen loading script)
├── docs/                # Project documentation (this cheatsheet)
├── vite-plugins/
│   └── mockPlugin.ts    # Vite dev Mock middleware
├── vite.config.ts       # Vite config (aliases, define, Less, Mock plugin)
├── src/
│   ├── components/      # Shared components (Footer, RightContent, SelectLang, ...)
│   ├── layouts/         # AppLayout: ProLayout wrapper + auth guard
│   ├── locales/         # i18n resources (8 languages)
│   ├── pages/          # Page components (with page-level _mock.ts)
│   ├── routes/         # Route meta, route table, menu data, icon map
│   ├── services/       # API service layer
│   ├── stores/         # Zustand global state
│   ├── i18n/           # i18next init + umi compatibility layer
│   ├── utils/          # request, format, chinaDivision, ...
│   ├── access.ts       # Permission definitions
│   └── main.tsx        # Application entry
└── tailwind.css
```

**Path aliases:**

| Alias | Maps to |
|-------|---------|
| `@/*` | `./src/*` |
| `@root/*` | `./` (project root) |

## Routing & Menu

**Route meta** lives in `src/routes/meta.ts`, 1:1 with the original template route table:

```ts
// File: src/routes/meta.ts
export const routes: AppRouteMeta[] = [
  {
    path: '/welcome',
    name: 'welcome',      // maps to the menu.welcome i18n key
    icon: 'home',
    lazy: () => import('@/pages/Welcome'),
  },
  {
    path: '/admin',
    name: 'admin',
    icon: 'crown',
    access: 'canAdmin',  // route-level permission
    routes: [...],
  },
  { path: '/', redirect: '/dashboard/analysis' },
];
```

The route table in `src/routes/index.tsx` is assembled with `createBrowserRouter`: routes with `layout: false` are flat-mounted, the rest are nested under the `AppLayout` parent route. The menu tree is built by `src/routes/menuData.ts` from route meta filtered by permissions; string icons are mapped to `@ant-design/icons` components via `src/routes/iconMap.tsx`.

**Navigation (React Router 7):**

```tsx
import { Link, useNavigate, useLocation, useSearchParams } from 'react-router-dom';

const navigate = useNavigate();
navigate('/dashboard');   // navigate
navigate(-1);            // go back

const location = useLocation();           // current route info
const [searchParams] = useSearchParams(); // query params
```

> 💡 The `name` field maps to the `menu.xxx` i18n key, translated in `src/locales/`.

## Layout

**Theme defaults** live in `config/defaultSettings.ts`:

```ts
export default {
  navTheme: 'light',        // light / realDark
  colorPrimary: '#1677ff',  // primary color
  layout: 'mix',           // side / top / mix
  contentWidth: 'Fluid',    // Fluid / Fixed
  fixedHeader: false,       // sticky header
  fixSiderbar: true,         // sticky sider
  title: 'Ant Design Pro',
};
```

**Layout shell** in `src/layouts/AppLayout.tsx`: wraps `<Outlet />` with `ProLayout`, including the auth guard, header `RightContent`, footer `Footer`, and the right-side `SettingDrawer`.

**Page container:**

```tsx
import { PageContainer } from '@ant-design/pro-components';

const Page = () => (
  <PageContainer header={{ title: 'Page title' }} content="Page description">
    {/* page content */}
  </PageContainer>
);
```

**Custom areas:** top-right `src/components/RightContent`, bottom `src/components/Footer`.

## Global State

**Initial state (Zustand)** lives in `src/stores/initialState.ts`, replacing the original `getInitialState`:

```ts
// Read in a component
import { useInitialStateStore } from '@/stores/initialState';

const settings = useInitialStateStore((s) => s.settings);
const currentUser = useInitialStateStore((s) => s.currentUser);
```

On startup, `bootstrapInitialState()` (called in `src/main.tsx`) decides whether to fetch the current user based on the current route and writes the result into the same store.

**Server state (React Query):**

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

> 💡 The global `QueryClient` is created in `QueryClientProvider` in `src/main.tsx`.

## Request

**Request wrapper** lives in `src/utils/request.ts`, based on an axios instance:

```ts
import { request } from '@/utils/request';

// GET
const data = await request<{ data: API.CurrentUser }>('/api/currentUser');

// POST
await request('/api/users', { method: 'POST', data: { name: 'test' } });
```

- The response interceptor returns the response body JSON; business errors (body `success === false`) throw a `BizError`.
- Tiered error handling lives in `src/requestErrorConfig.ts` (message / notification).
- Dev `baseURL` is empty (local Mock); production points to the remote demo API.

Service-layer functions live in `src/services/ant-design-pro/`, each calling `request` internally.

## Access / Permissions

**Define permissions** in `src/access.ts`:

```ts
export default function access(initialState: { currentUser?: API.CurrentUser } | undefined) {
  const { currentUser } = initialState ?? {};
  return {
    canAdmin: currentUser && currentUser.access === 'admin',
  };
}
```

**Route-level:** add an `access` field to route meta; `AppLayout` filters the menu and accessible routes accordingly.

**Component-level:** read the permission map (built from `access({ currentUser })`) and conditionally render in the component.

## Internationalization

**Init** in `src/i18n/index.ts`, default locale `zh-CN`, with 8 built-in languages: `zh-CN`, `zh-TW`, `en-US`, `ja-JP`, `pt-BR`, `id-ID`, `fa-IR`, `bn-BD`.

**File structure:**

```
src/locales/
├── zh-CN.ts        # zh entry (aggregates slices)
├── zh-CN/
│   ├── menu.ts     # menu translations
│   ├── pages.ts    # page translations
│   └── ...
├── en-US.ts
└── en-US/
    └── ...
```

**Usage (compatibility layer `src/i18n/intl.tsx`):**

```tsx
import { useIntl, FormattedMessage } from '@/i18n/intl';

// Hook
const intl = useIntl();
intl.formatMessage({ id: 'menu.welcome' });

// Component
<FormattedMessage id="menu.welcome" />
```

**Switch locale:**

```tsx
import { setLocale, getLocale, getAllLocales } from '@/i18n/intl';

setLocale('en-US');   // switch, persisted to localStorage
const lang = getLocale();
```

> 💡 The locale preference is stored under the `antd_pro_locale` key.

## Styling

**Tailwind CSS v4:** use classes directly:

```tsx
<div className="flex items-center gap-4 p-6 rounded-lg bg-white" />
```

**antd-style (CSS-in-JS):**

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

**Less / global styles:** global styles in `src/global.less`; `src/global.style.ts` injects global token styles via antd-style.

**Dynamic theme:** in dev you can switch nav theme, primary color, etc. live via the `SettingDrawer` on the right.

> 💡 The three approaches coexist: Tailwind for layout, antd-style for consuming theme tokens, Less only for legacy global styles.

## Mock

**Mock middleware** lives in `vite-plugins/mockPlugin.ts`, intercepting `/api/**` requests as a Vite dev server middleware:

- **Global Mock**: `.ts` files under `mock/`.
- **Page-level Mock**: `src/pages/**/_mock.ts`, colocated with the page.

**Mock format (express-style req / res):**

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

- The key is `METHOD /path`; omitting the method matches all methods; path params are declared as `:param`.
- A handler can be a function, or directly an object / array used as the response body.

## Common Tasks

### Add a new page

```bash
# 1. Create the page component
#    src/pages/my-page/index.tsx

# 2. Register in route meta
#    src/routes/meta.ts
#    { path: '/my-page', name: 'myPage', icon: 'file', lazy: () => import('@/pages/my-page') }

# 3. Add menu i18n (if it should appear in the menu)
#    src/locales/zh-CN/menu.ts  → menu.myPage: 'My Page'
#    src/locales/en-US/menu.ts  → menu.myPage: 'My Page'
```

### Add global state

Define a store with Zustand `create` under `src/stores/` and read it via selectors in components; shared initial user info and theme settings are consolidated in the `initialState` store.

### Add a Mock endpoint

```bash
# Global Mock: mock/api.ts
# Page-level Mock: src/pages/my-page/_mock.ts

# Format:
# export default { 'GET /api/my-data': { data: [] } }
```

## Notes

- **Path aliases**: `@/*` → `./src/*`, `@root/*` → `./`.
- **Type check**: `npm run build` already runs `tsc --noEmit`; it does not emit `.js` into the source tree. You can also run `./node_modules/.bin/tsc --noEmit` directly.
- **No Umi runtime**: this project does not depend on `@umijs/max`; routing, state, request, i18n, access, and Mock are all implemented by the self-built modules above.
- **Style priority**: Tailwind (layout) > antd-style (theme tokens) > local component styles > Less (legacy global only).
- **Commit convention**: follow [Conventional Commits](https://www.conventionalcommits.org/), e.g. `feat:`, `fix:`, `chore:`, `refactor:`.
