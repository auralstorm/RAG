# Enterprise Agentic AI Platform — V1.1 文档包

> 公共字段、状态、事件、权限与迁移映射见 [统一契约与跨版本演进规则](../../architecture/统一契约与跨版本演进规则.md)；本文件描述本版能力及增量，具体实现须通过契约与升级验收。

**版本：** V1.1 — Agent Platform Foundation  
**用途：** 研发启动、架构评审、任务拆分、测试与阶段验收  
**文档状态：** 研发设计基线草案；具体排期、性能目标与 Adapter 实现深度需在启动会/POC 后冻结。

## 文档清单

| 文件 | 内容 |
|---|---|
| 01-agent-runtime-detailed-design.md | LangGraph Runtime、Agent Run/Step、状态机、Checkpoint、恢复、并发、预算、Trace |
| 02-tool-gateway-and-connector-framework.md | Tool Contract、Gateway、Policy、幂等、REST/SQL/MCP Adapter、Mock Connector |
| 03-memory-context-and-state-management.md | Conversation Context、Summary、Task Memory、Checkpoint、Token Budget、生命周期 |
| 04-database-api-and-contract-design.md | PostgreSQL 实体、状态枚举、API、SSE、事件、Policy Contract、迁移策略 |
| 05-code-structure-and-development-backlog.md | 代码目录、模块依赖、Epic、Task、优先级和任务验收 |
| 06-complete-implementation-plan-and-acceptance.md | 阶段计划、逐项任务、测试矩阵、Exit Criteria、发布准入 |

## 与 V1.0 的关系

V1.1 在 V1.0 已有能力上增量建设，不重做：
- 企业身份认证、基础 RBAC 和知识库 ACL；
- Model Gateway Facade + LiteLLM；
- LlamaIndex RAG Engine 与 Retriever API；
- Elasticsearch Search Gateway；
- PostgreSQL、Redis、RabbitMQ/Celery、对象存储；
- Chat/Admin 双入口基础框架；
- OpenTelemetry/Phoenix 基础 Trace 和操作审计。

## V1.1 范围边界

**本版本建设：**
- 单 Agent Runtime（LangGraph Adapter）；
- Agent Run/Step、事件、Checkpoint、取消和恢复；
- Tool Gateway、Tool Contract、Policy 扩展；
- Mock Connector，以及 REST/SQL/MCP 的受控适配边界；
- 基础 Summary/Task Memory/Context Budget；
- Agent Trace、并发与预算治理；
- Chat 中的最小 Agent 使用入口。

**明确不建设：**
- V1.2 可视化 Agent Builder、Playground、完整 Agent Registry/发布中心；
- V1.3 Planner、Multi-Agent、复杂 Agentic RAG；
- V1.4 完整 Workflow Engine、生产业务写操作和企业审批中心。

## 技术基线

- Python + FastAPI
- LangGraph（Agent Runtime）
- LlamaIndex（RAG Engine，Agent 通过 Retriever Contract 调用）
- 自研 Model Gateway Facade + LiteLLM
- PostgreSQL、Redis、RabbitMQ + Celery
- Elasticsearch（经 Search Gateway）
- OpenTelemetry + Phoenix
- Docker + uv

技术选型沿用既定基线。POC 用于验证关键路径；若硬性要求不满足，按 ADR 流程调整，不无故重开选型。

## 阅读顺序

建议先阅读 01、02、03，理解运行时、工具和状态；再阅读 04 对齐数据/API；由研发负责人使用 05 拆分任务；最后使用 06 管理阶段交付和验收。

## 执行注意事项

1. 所有 Tool 调用必须经过 Tool Gateway 和 Policy Engine。
2. Agent 不得直接访问 Elasticsearch、数据库或外部系统。
3. LangGraph State 不作为平台公共业务契约。
4. Redis 和 RabbitMQ 不作为唯一业务状态来源。
5. V1.1 默认使用 Mock Tool，不开放生产副作用写操作。
6. 恢复 Run 时必须重新校验身份、权限、配置和 Tool 版本。
7. V1.0 的安全、删除、审计和隐私规则继续有效。
8. 性能和容量目标必须由目标环境压测确定，本文不虚构 SLA。
