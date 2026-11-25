# Admin Pro 风格框架与现有页面重构

日期：2026-11-25。基线：`6226562`（双应用当前权限联调）。

## 交付范围

按用户确认，保留 Vite、React Router、pnpm workspace 与双应用独立部署，使用 Ant Design 和 ProComponents 复刻 Ant Design Pro 的管理台结构。本轮仅迁移已实现的登录、服务连接和访问状态页面；模型、知识库、用户角色、审计等业务继续按原计划交付，不新增演示菜单或虚构指标。

官方参考：[Ant Design Pro](https://github.com/ant-design/ant-design-pro)、[ProComponents](https://github.com/ant-design/pro-components)。Admin 锁定 `@ant-design/pro-components@3.1.15-9`，其 peerDependencies 支持 antd 6 和 React 18+。这是预发布版；后续升级需重新验证组件行为、严格类型、包体和两个应用消费者，不能直接沿用仍指向 antd 4/5 兼容线的 npm latest 标签。

## 实现与兼容

- Admin 内部拥有 ProLayout、PageContainer、品牌、导航、登录和 Result 状态页面。浅色、中文、现有蓝色主色；顶部操作区、可折叠侧栏、移动端抽屉、面包屑与页面标题使用正式组件 API。
- `routes/admin-pages.tsx` 组合已实现页面的路由与加载入口；页面名称、标题、图标及权限元数据由对应模块提供，避免页面反向依赖路由注册表。保留 `/login`、`/admin` 和仅开发环境的 `/preview`。布局与业务页面按路由懒加载。
- Chat 和 Admin 统一采用轻量 `pages/` 与 `modules/` 结构，目录和文件命名遵循 [前端代码规范](../../../standards/前端代码规范.md)；模块按需创建，不强制 domain 或状态库。
- 共享 `SessionBoundary` 增加可选 `renderStatus` 展示回调和 `SessionStatusProps` 类型。回调只接收已有判断产生的状态与恢复操作，不参与主体、权限、期限和 Policy 版本校验。Chat 沿用默认展示。
- 公共 API 客户端、Cookie 会话、CSRF、授权查询及取消/过期响应处理保持原协议。后台权限丢失时同时卸载导航与业务内容。没有后端 HTTP/数据库迁移；没有复制模板的 Mock 登录、浏览器 Token 或 Umi 运行时。

## 可重复验收入口

```bash
make install
make check
pnpm exec playwright install --with-deps chromium
# 本机还需要 nginx 和可用的 Docker；make check 已生成两个生产构建。
make frontend-e2e
```

浏览器入口使用 `backend/tests/test_frontend_browser.py` 的既有 RBAC/认证 fixtures，建立随机测试数据库和合成账号。临时 FastAPI 及两个 Nginx 进程监听本机临时端口；Nginx 使用仓库部署配置派生的独立静态服务，指向真实构建产物。结束后停止进程、删除随机数据库并清理测试卷，不修改开发身份配置或账号。

Playwright 从仓库锁文件导入，不依赖本机绝对安装路径。可选 `ENTERPRISE_RAG_BROWSER_EXECUTABLE` 指定已安装浏览器；CI 使用 Playwright 安装的 Chromium。`make infra-test` 排除 `frontend_e2e`，CI 在普通检查及基础设施测试后单独执行浏览器验收，上传截图结果。

验收覆盖：三种后台角色、员工拒绝与退出、无 KB 授权 Chat 入口、生产深链与刷新、菜单选中/折叠、移动抽屉键盘操作与焦点、权限 503 恢复、混合主体拒绝、真实角色撤销、会话失效、API 故障重试、HttpOnly/浏览器存储、生产预览关闭、静态资源 404/MIME，以及 1440/768/390/320 宽度。

## 验证记录

2026-11-25 本地验收：

- `make check`：通过。Ruff、ESLint、Pyright、TypeScript、Prettier、后端测试（303 项通过，75 项按标记排除）、Vitest（11 个文件 / 98 项通过）、生产构建、HTTP 契约及仓库检查均通过。
- `make frontend-e2e`：通过，1 项生产浏览器验收通过；临时 PostgreSQL、API 与 Chat/Admin 静态服务已清理。
- Vite 构建有非阻断的大 chunk 提示：Admin dashboard 511.68 KB、Chat 主 chunk 660.82 KB（压缩后分别为 168.06 KB、217.03 KB）。

截图位于被忽略的 `.poc-results/frontend/admin-pro/`，不作为业务数据或提交制品。

平台账号登录由 P1-04 验收；飞书等外部企业登录暂缓，完整 V1.0 管理业务与生产发布继续按对应阶段验收。
