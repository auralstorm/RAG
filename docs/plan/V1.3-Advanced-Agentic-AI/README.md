# Enterprise Agentic AI Platform — V1.3 Advanced Agentic AI

> 公共字段、状态、事件、权限与迁移映射见 [统一契约与跨版本演进规则](../../architecture/统一契约与跨版本演进规则.md)；本文件描述本版能力及增量，具体实现须通过契约与升级验收。

## 版本定位

V1.3 在 V1.1 Agent Runtime 和 V1.2 Agent Development Platform 之上，建设高级 Agent 执行能力：Planning、Task Decomposition、Agentic RAG、Multi-Agent、Checkpoint、Retry、Human-in-the-loop、Guardrails、Evaluation 与 Observability。

## 文档清单

1. `01-advanced-agent-runtime-and-execution-architecture.md` — Runtime、状态机、Planner、Executor、Checkpoint、预算与安全。
2. `02-planning-task-decomposition-and-multi-agent.md` — 任务拆解、Supervisor-Worker、委派契约、并发和冲突处理。
3. `03-agentic-rag-and-evidence-engineering.md` — Query Decomposition、多跳检索、Evidence、Claim Verification。
4. `04-human-in-the-loop-guardrails-and-recovery.md` — 人工介入、审批、Guardrails、Prompt Injection 和恢复。
5. `05-multi-agent-evaluation-observability-and-quality.md` — 评测体系、Trace、事件流、发布门禁。
6. `06-database-api-contracts-and-code-structure.md` — 数据模型、API、内部 Contract、代码结构和一致性。
7. `07-complete-implementation-plan-and-acceptance.md` — 里程碑、研发顺序、测试、阻断项和 DoD。

## 与前序版本的关系

- V1.0：企业知识库与 Standard RAG。
- V1.1：Agent Runtime、Tool Gateway、Connector Contract、Memory 和基础执行。
- V1.2：Agent Registry、Definition、Builder、Playground、Evaluation、Release Governance。
- V1.3：高级规划、多步执行、Agentic RAG、Multi-Agent、恢复和人工介入。
- V1.4：企业 Workflow Engine、审批流程、真实企业系统集成和业务动作。

## 技术基线沿用

Python + FastAPI、React + TypeScript、LlamaIndex、LangGraph、Elasticsearch（Search Adapter 隔离）、PostgreSQL、Redis、RabbitMQ + Celery、S3 compatible / MinIO、Model Gateway Facade + LiteLLM、OpenTelemetry + Phoenix、RAGAS + Golden Dataset、uv、Docker。

## 关键架构约束

1. Agent Runtime 与 RAG Engine 分离；Agent 通过 Retriever API 调用 RAG。
2. 所有 Tool 调用经过 Tool Gateway 和 Policy Engine。
3. Planner 输出先校验再执行，不能直接执行模型自由文本。
4. Multi-Agent 默认最多两层（Supervisor → Worker），有界并发和预算。
5. Worker 仅获得显式委派的最小权限。
6. Checkpoint 不保存 Secret；恢复时重新校验身份和权限。
7. 高风险 Tool 必须经过服务端审批门禁；V1.3 不实现通用企业审批流程。
8. LangGraph 管 Agent 内部执行；V1.4 Workflow Engine 管企业确定性流程。
9. 不展示模型隐藏思维链；展示结构化 Plan、执行事件、工具摘要和证据。
10. V1.2 已发布 Agent 在无 V1.3 扩展配置时继续以安全默认值运行。

## 重要说明

文档中的参数和阈值是工程设计基线，具体数值应通过 POC、Golden Dataset、压测和安全评审确定，不应未经验证直接视为生产 SLA。

## 本轮兼容与范围规则

Run/Step/Checkpoint 在 V1.1 上增量扩展，保留幂等、预算、原始配置、序号和 TTL；公共 status 与 execution_phase 分离。Evaluation 复用 V1.2 数据和门禁，HITL 承接 V1.1 最小审批协议。Multi-Agent 依 M0/M3 的业务收益准入和范围 ADR 管理，不自动延后，也不按版本号直接投入实现。

采用单一企业内部部署，企业内资源按当前身份、角色与 ACL 授权；本版不依赖未交付的 V1.4 Workflow/Approval Center。
