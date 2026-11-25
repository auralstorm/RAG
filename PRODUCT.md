# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

员工通过 Chat 查阅企业知识；管理员通过独立 Admin 应用管理知识与平台资源。身份和资源权限由服务端计算。

## Product Purpose

单一企业内部部署的知识问答平台。V1.0 目标是可追溯、权限正确的 Standard RAG；范围与验收遵循 [总体路线图](docs/plan/总体版本路线图与架构演进规划.md)。

## Operating Context

同一 Monorepo 管理两个 Vite + React + TypeScript 应用和 FastAPI 后端。当前开发试点是 IT 内部服务台，开发登录先使用本地测试身份源，再按实际需求接入飞书。

## Capabilities and Constraints

登录页面、路由及状态界面属于 P1-02；P1-03/P1-04 已提供显式身份映射、本地测试身份源与可撤销平台会话，两个前端已接入本地登录、恢复、续期与登出。真实企业 OIDC 与完整 RBAC 仍待接入和验收。问答模拟仅在开发 `/preview` 加载，受保护问答页面不加载固定答案。页面不得把本地测试来源表现为企业 SSO 或真实检索。

## Brand Commitments

项目名 EnterpriseRag，员工入口称企业知识助手，管理入口称企业知识管理。界面使用中文，延续已确认的 Ant Design 组件与主题机制。

## Accessibility & Inclusion

关键控件需要键盘访问、表单标签、焦点提示与可理解的错误和加载状态，依据 [前端规范](docs/standards/前端代码规范.md)。

## Evidence on Hand

产品事实来自用户批准的项目规范、[V1.0 实施计划](docs/plan/V1.0-MVP/06-完整研发实施计划与阶段验收标准.md)、[P0-05 验收口径](docs/plan/V1.0-MVP/implementation/P0-05.md) 和 [P1-04 实施记录](docs/plan/V1.0-MVP/implementation/P1-04.md)。实际登录 API 与本地测试登录已具备验证证据；尚无企业身份源配置或品牌图片，不补造供应商接入和生产验收证据。
