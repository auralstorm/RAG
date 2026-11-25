# Chat/Admin 静态部署验收

两个应用分别构建、分别提供静态服务，共用后端 API。此目录提供可直接运行的 Nginx 本地部署配置，包含应用路由回退、静态资源 MIME 类型和同源 API 代理。真实生产环境的域名、TLS、受信任代理及身份 Cookie 策略在认证接入和上线任务中配置。

在根目录运行 `pnpm build`，安装 Nginx 后，在两个终端分别运行：

```bash
mkdir -p .poc-results/frontend
nginx -p "$PWD/" -c infra/frontend/chat.conf -g 'daemon off; error_log stderr;'
```

```bash
mkdir -p .poc-results/frontend
nginx -p "$PWD/" -c infra/frontend/admin.conf -g 'daemon off; error_log stderr;'
```

Chat 使用 <http://127.0.0.1:4173>，Admin 使用 <http://127.0.0.1:4174>。配置以仓库根目录作为 Nginx prefix；部署到其他路径时分别调整 root。两个配置独立启动和停止，不需要共享一个 Nginx 进程。`Ctrl-C` 停止对应前台服务。

默认浏览器 API 地址为 `/backend/`，Nginx 将 `/backend/health/live` 转发至 `http://127.0.0.1:8000/health/live`。运行 `make dev-backend` 后可检查代理；后端关闭时应返回 502，不能回退成 HTML 或声称服务已连接。实际后端地址变化时修改对应 proxy_pass，保留末尾 `/`。

Vite 开发服务使用相同 `/backend/` 前缀，由应用 `.env.example` 的 `API_PROXY_TARGET` 控制代理目标。`VITE_API_BASE_URL` 仅配置公开浏览器地址，可为相对路径或 HTTP(S) 地址，构建时写入产物；`API_PROXY_TARGET` 仅在开发服务器使用。直连跨域地址需要后端显式允许对应来源。Chat 的客户端入口已准备，业务调用随认证/问答 API 接入；不发起无意义的后台探测。

验收步骤：

1. 直接打开或刷新 `/login`、Chat 的 `/chat`、Admin 的 `/admin`；静态服务器应返回各自 index.html，匿名用户由应用跳转登录。
2. 打开未知路径应展示应用的“页面不存在”；生产 `/preview` 同样不可用。
3. `/assets/不存在.js` 应返回 404，实际 JS/CSS 返回正确 Content-Type，不能返回 index.html。
4. 两个 `/backend/health/live` 应返回后端 JSON；API 失败应保留 HTTP 失败语义。
5. 开发 Admin 登录页进入 `/preview`，检查公开 API 连通性表格的初始空态、检查中、成功、失败后重试。此预览不会建立登录态，也不加载业务或授权数据。

P1-02 的本地部署验证不代表生产发布、真实登录或完整 P1/M1 验收。[实施记录](../../docs/plan/V1.0-MVP/implementation/P1-02.md)

## 自动浏览器验收

安装 Nginx、准备可用 Docker，运行 `make check` 生成生产构建，再运行 `pnpm exec playwright install --with-deps chromium` 和 `make frontend-e2e`。该入口启动隔离数据库、真实后端和两个临时 Nginx 静态服务，验证认证权限、Admin 导航与故障恢复、双应用回归及资源服务规则。端口自动选择，测试不使用或修改开发账号。

截图输出到 `.poc-results/frontend/admin-pro/`。测试默认使用 Playwright Chromium；本机可通过 `ENTERPRISE_RAG_BROWSER_EXECUTABLE` 指定其他已安装的兼容浏览器。[范围与验证记录](../../docs/plan/V1.0-MVP/implementation/admin-pro-ui.md)
