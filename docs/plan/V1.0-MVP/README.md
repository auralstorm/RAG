# Enterprise Agentic AI Platform — 技术设计文档包

> 公共字段、状态、事件、权限与迁移映射见 [统一契约与跨版本演进规则](../../architecture/统一契约与跨版本演进规则.md)；本文件描述本版能力及增量，具体实现须通过契约与升级验收。

版本：V1.0  
日期：2026-11-23

本包含六份相互关联的 Markdown 设计与实施文档：

1. `01-rag-engine-detailed-design.md` — RAG Engine 详细技术设计
2. `02-agent-runtime-detailed-design.md` — Agent Runtime 详细技术设计
3. `03-database-and-api-design.md` — 数据库与 API 设计
4. `04-poc-acceptance-and-adr.md` — POC 技术验收与 ADR 冻结
5. `05-code-structure-and-backlog.md` — 项目代码结构及研发任务拆分
6. `06-完整研发实施计划与阶段验收标准.md` — 完整研发实施计划与阶段验收

## 架构基线

- Backend：Python + FastAPI，依赖使用 uv 管理
- Frontend：Vite + React + TypeScript；Chat/Admin 两个独立应用
- RAG：LlamaIndex
- Agent Runtime：LangGraph
- Parser：Docling 默认；独立 POC-02 已按用户决定延后，md/DOCX/PDF 的实际解析验证在 P3-01 正式集成时完成，实际缺口再触发 MinerU PDF 备选验证，见 [POC-02](04-poc-acceptance-and-adr.md)
- Search：Elasticsearch 默认，OpenSearch 保留 POC 候选
- Model Gateway：自研 Facade + LiteLLM
- Async：RabbitMQ + Celery
- DB：PostgreSQL；Cache：Redis；Object Storage：S3 compatible / RustFS
- Observability：OpenTelemetry + Phoenix
- Evaluation：RAGAS + Golden Dataset
- 工程组织：Monorepo；前端使用 pnpm workspace 管理两个应用与公共包，依据 [ADR-0014](../../adr/0014-monorepo-and-independent-frontend-apps.md)
- 部署形态：两个前端分别部署，共用模块化后端与独立 Worker，第一期不全面微服务化

## 重要说明

文档是基于当前已确认架构基线编写的研发设计 V1.0。POC 结果尚待实际执行，因此文中涉及性能阈值、模型表现、解析质量和部署容量的内容均需在目标环境中验证；POC 通过后再冻结具体版本、参数和 SLO。

建议阅读顺序：统一契约规则 → RAG Engine → Agent Runtime → 数据库与 API → POC/ADR → 代码结构与研发任务 → 完整实施计划。

## 实施记录

- [P0-01 工程初始化与本地验收](implementation/P0-01.md)：记录实际命令、结果和待执行的远程检查，不代替阶段 Exit Criteria。
- [P0-02 Docker 开发环境与就绪检查](implementation/P0-02.md)：记录依赖启动、持久化、故障恢复和重置验证。
- 试点口径、问答样例和 Chat/Admin 验收流程见 [P0-05 MVP 需求与验收口径](implementation/P0-05.md)。
- [P1-01 后端工程底座](implementation/P1-01.md) 记录数据库迁移、事务边界和模块依赖验证。
- [P1-02 前端基础交付](implementation/P1-02.md) 记录双应用登录/路由、受控状态、基础表格、真实 API 连通性及本地静态部署验收；完整任务待 P1-04/P1-05 联调，不代表真实认证闭环。
- [P1-04 平台账号与身份映射](implementation/P1-04.md) 记录正式平台密码登录、受控 CLI 建号、会话续期与撤销、双应用入口隔离及未来外部身份源边界。
- [P1-05 RBAC 与权限执行](implementation/P1-05.md) 记录固定矩阵、自定义角色边界、目的隔离 ACL、即时撤权、确认/审计与显式首位管理员配置。
- [P1-06 操作审计基础能力](implementation/P1-06.md) 记录统一追加写入、登录及权限变更定位、受保护查询、防修改与审计失败回滚。
- [P1-07 基础健康检查与可观测性](implementation/P1-07.md) 记录受控日志、SDK 指标、认证 Phoenix 导出、实际依赖观测与传播/隐私边界。
- [Chat 页面与开发回复来源](implementation/chat-ui.md) 记录目录整改、会话交互、开发 mocks 隔离及生产未接入状态；正式登录、RAG 与会话持久化继续按实施计划交付。
- [Admin Pro 风格框架](implementation/admin-pro-ui.md) 记录保留 Vite 的 ProComponents 布局、现有页面迁移与隔离浏览器验收；后续管理业务按原计划推进。

对象存储已按用户确认采用 RustFS，见 [ADR-0015](../../adr/0015-rustfs-object-storage.md) 与 [替换实施记录](implementation/rustfs-object-storage.md)。选型和开发验收已分开记录，POC-08 的生产准入检查继续在 P0-03 完成。

技术 POC 的执行顺序、功能证据及待确认项见 [P0-03 实施进度](implementation/P0-03.md)。
