# Enterprise Agentic AI Platform — V1.2 Agent Development Platform

> 公共字段、状态、事件、权限与迁移映射见 [统一契约与跨版本演进规则](../../architecture/统一契约与跨版本演进规则.md)；本文件描述本版能力及增量，具体实现须通过契约与升级验收。

## 1. 版本定位

V1.2 在 V1.1 Agent Platform Foundation 之上，交付 Agent 开发与管理平台能力：

**Agent Registry → Definition → Prompt / Tool / KB Binding → Playground → Evaluation → Release → Chat 使用 → Trace / Rollback**

目标是让开发者无需修改平台核心 Runtime，即可配置、测试和发布不同业务 Agent。

## 2. 文档清单

| 文件 | 内容 |
|---|---|
| 01-agent-registry-definition-and-lifecycle.md | Agent Registry、声明式 Definition、版本生命周期、Prompt 与 Tool Binding |
| 02-agent-builder-playground-and-admin-ux.md | Admin Agent Builder、Playground、Evaluation 与发布中心 UX |
| 03-agent-evaluation-testing-and-release-governance.md | Dataset、指标、评分、回归、发布 Gate 与评测执行 |
| 04-database-api-and-contract-design.md | PostgreSQL 模型、API、事件、Contract 与迁移策略 |
| 05-code-structure-and-development-backlog.md | 模块边界、仓库结构、Epic、Task、DoD 与风险 |
| 06-complete-implementation-plan-and-acceptance.md | 阶段计划、Entry/Exit Criteria、测试矩阵、发布与回滚 |

## 3. 依赖版本

- V1.0：企业知识库与 Standard RAG
- V1.1：Agent Runtime、Tool Gateway、Connector Framework、Memory / Context / State
- V1.2：Agent Development Platform

如果 V1.1 的 Runtime Facade、Tool Policy、Memory 和 Trace Contract 尚未验收，先补齐上游依赖，不应在 V1.2 复制实现。

## 4. 技术基线（沿用，不重新选型）

- Backend：Python + FastAPI
- Frontend：React + TypeScript
- Agent Runtime：LangGraph
- RAG：LlamaIndex
- Search：Elasticsearch（Search Adapter 隔离）
- Model Gateway：自研 Facade + LiteLLM
- Async：RabbitMQ + Celery
- Cache：Redis
- Business DB：PostgreSQL
- Object Storage：S3 Compatible / MinIO
- Observability：OpenTelemetry + Phoenix
- Evaluation：RAGAS + Golden Dataset（V1.2 增加 Agent 任务与治理指标）
- Dependency：uv
- Container：Docker

以上是项目既定基线；具体版本、参数、性能指标需通过项目 POC、兼容性测试和 ADR 验收，不在本包中虚构“已通过”结论。

## 5. 核心架构原则

1. Agent Definition 使用声明式 Schema，不允许任意代码执行。
2. Agent Version 发布后不可变；Run 固定版本快照。
3. Tool 调用必须经过 Tool Gateway 和 Policy Engine。
4. Playground 服务端强制 Sandbox Policy，默认 Mock / 只读。
5. Evaluation 使用独立队列、预算和 Trace Group，不挤占在线流量。
6. Release Gate 阻止硬门禁失败的版本发布。
7. Chat 只展示用户有权访问的已发布 Agent。
8. 保持 Chat + Admin 双入口，不新增一级产品入口。
9. 继续模块化单体，异步 Worker 可独立部署，不提前全面微服务化。
10. 隐私、审计和数据生命周期沿用 V1.0/V1.1 规则。

## 6. 版本边界

### V1.2 包含
- Agent Registry / Definition / Version
- Prompt Management
- Tool / Model / KB / Memory Binding
- Admin Agent Builder
- Playground 与 Sandbox
- Dataset / Evaluation / Report / Compare
- Release Gate / Publish / Rollback
- Chat 已发布 Agent 目录和调用入口

### 后续版本
- V1.3：Planner、Multi-Agent、Advanced Agentic RAG、Supervisor、Human-in-the-loop
- V1.4：企业 Workflow、真实业务系统生产 Connector、审批和业务动作
- V2.0：企业级规模化、HA、DR、统一治理与成本运营

## 7. 推荐阅读顺序

1. 先读 01，确认 Agent 定义和版本语义。
2. 读 02，确认开发者工作台和使用体验。
3. 读 03，确认评测指标与发布门禁。
4. 读 04，冻结数据库和 API Contract。
5. 读 05，拆分开发任务。
6. 读 06，制定 Sprint、阶段验收和上线计划。

## 8. 重要实施提醒

- 本文档是 V1.2 研发基线，不代表代码已实现或 POC 已通过。
- 版本、指标阈值、SLO、并发和成本预算必须由实际测试数据确定。
- Agent Definition Schema 和核心 API 在 Phase 0 评审后冻结。
- 所有发布版本需记录 Schema、Prompt、Model Profile、Tool Binding、KB 与策略快照引用。
- 若现有 V1.1 实际接口与本文档不一致，先通过 ADR 做兼容设计，不要直接复制一套平行接口。
