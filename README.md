# EnterpriseRag

单企业内部部署的知识与 AI 平台。本仓库按 V1.0 MVP 的 [实施计划](docs/plan/V1.0-MVP/06-完整研发实施计划与阶段验收标准.md) 推进，当前提供 FastAPI、Chat/Admin 独立应用、公共包和工程检查入口。业务功能和身份登录按后续任务交付，基础设施使用本项目的 Docker 编排，对象存储已按 [ADR-0015](docs/adr/0015-rustfs-object-storage.md) 采用 RustFS（S3 协议）。

## 工具链

| 工具 | 锁定版本 |
|---|---|
| Node.js | 22.22.0，见 `.node-version` |
| pnpm | 10.34.9，见 `package.json` 的 `packageManager` |
| Python | 3.12.16，见 `.python-version`，uv 可自动下载 |
| uv | 0.13.8，CI 使用相同版本 |

Python 包使用根目录 `uv.lock`；前端应用和公共包使用根目录 `pnpm-lock.yaml`。直接依赖采用固定版本；`make install` 按锁文件安装。

## 安装与启动

准备上述工具后，在仓库根目录运行：

```bash
make install
cp .env.example .env
```

后端已有可用于启动的开发默认配置，`.env` 用于本地覆盖。真实环境文件已被忽略，提交时仅维护无凭据的 `.env.example`。

分别打开三个终端，在根目录启动：

```bash
make dev-backend
```

```bash
make dev-chat
```

```bash
make dev-admin
```

| 服务 | 本地地址 |
|---|---|
| API 存活检查 | <http://127.0.0.1:8000/health/live> |
| OpenAPI / Swagger | <http://127.0.0.1:8000/docs> |
| Chat | <http://127.0.0.1:5173> |
| Admin | <http://127.0.0.1:5174> |

`/health/live` 仅表示 API 进程能够响应请求。依赖启动与就绪检查见 [基础设施说明](infra/README.md)，使用 `make infra-up` 启动本项目依赖，再启动后端。两个前端当前是独立启动壳；应用层后续通过公共客户端和各自 `VITE_API_BASE_URL` 接入业务 API。

## 目录与依赖

```text
backend/app/                # FastAPI 装配、配置及 HTTP 入口
backend/tests/              # API 与配置验证
frontend/apps/chat/         # 员工端，独立启动和构建
frontend/apps/admin/        # 管理端，独立启动和构建
frontend/packages/ui/       # 公共展示组件与主题
frontend/packages/api-client/ # HTTP 协议适配
frontend/packages/shared/   # 不依赖应用的公共类型与工具
infra/                     # Docker 编排、固定镜像与初始化配置
scripts/                   # 仓库检查脚本
docs/                      # 设计、计划、规范与实施证据
```

前端采用 create-vite 9.3.4 的 React TS 模板，React 19.3.1、Vite 8.3.6、TypeScript 6.0.3 和 Ant Design 6.7.2；基础 UI 在公共包统一维护。业务路由、数据缓存、全局状态、ProComponents 与 Ant Design X 在对应功能有实际需求时落实，版本与接口随实现记录。

应用通过公共包的正式 exports 使用能力。ESLint 检查应用间直接导入和公共包反向依赖应用；改公共包时，统一检查与构建会覆盖两个消费者。

## 验证入口

```bash
make check
```

该命令依次运行 Ruff、ESLint、格式检查、Pyright、TypeScript、pytest、Vitest、两个前端生产构建、本地文档链接检查及 Git 差异检查。

技术检索 POC 使用 `make poc-search`：启动独立 Elasticsearch、验证客户端 RRF 与权限/索引边界，并保存 `.poc-results/search/` 报告。普通测试不启动 Docker，完整 POC 状态见 [P0-03 进度](docs/plan/V1.0-MVP/implementation/P0-03.md)。

对象存储 POC 使用 `make poc-storage`：在独立 RustFS 项目验证受限身份、Service Account/STS、生命周期回收与空新卷备份恢复，并保存 `.poc-results/storage/` 报告。测试结束清理 POC 卷；使用测试端口，不能与 `make infra-test` 同时运行。功能证据与剩余准入见 [POC-08 记录](docs/plan/V1.0-MVP/implementation/POC-08-storage.md)。

需要针对变更检查时使用 `make lint`、`make format-check`、`make typecheck`、`make test` 或 `make build`。前端格式化使用 `pnpm format`，Python 格式化使用 `uv run --locked ruff format backend scripts`。

仓库检查脚本检查本地链接、误纳入版本控制的环境文件、常见 OpenAI Key 和私钥格式；它不替代专门的凭据扫描、权限测试或安全评审。历史审查原文和规划文档保留原有格式，前端 Prettier 范围不包含这些文档。

CI 配置见 [.github/workflows/ci.yml](.github/workflows/ci.yml)，执行相同 `make install` 和 `make check`，并用 commitlint 校验新增提交信息。服务端 CI 和 PR 的执行状态以实际运行结果为准。

## 开发协作

遵循 [AGENTS.md](AGENTS.md)、[Git 提交规范](docs/standards/git-提交规范.md) 和 [分支与评审规范](docs/standards/git-协作规范.md)。每项独立任务验证通过后创建本地提交；远程推送按用户明确授权执行。

完整文档见 [文档索引](docs/README.md)。实际进度与证据见 [P0-01 工程记录](docs/plan/V1.0-MVP/implementation/P0-01.md) 和 [P0-02 基础设施记录](docs/plan/V1.0-MVP/implementation/P0-02.md)，当前对象存储验证见 [RustFS 替换记录](docs/plan/V1.0-MVP/implementation/rustfs-object-storage.md)。
