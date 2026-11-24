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

对象存储已按用户确认采用 RustFS，见 [ADR-0015](../../adr/0015-rustfs-object-storage.md) 与 [替换实施记录](implementation/rustfs-object-storage.md)。选型和开发验收已分开记录，POC-08 的生产准入检查继续在 P0-03 完成。

当前进入 P0-03，已确认文档格式，百炼模型仅作为本次 POC 候选，执行顺序、功能证据及待确认项见 [P0-03 实施进度](implementation/P0-03.md)。
