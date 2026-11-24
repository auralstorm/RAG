# 04 — V1.2 数据库、API 与平台 Contract 设计

> 公共字段、状态、事件、权限与迁移映射见 [统一契约与跨版本演进规则](../../architecture/统一契约与跨版本演进规则.md)；本文件描述本版能力及增量，具体实现须通过契约与升级验收。

## 1. 设计边界

V1.2 基于 V1.0 PostgreSQL、Redis、RabbitMQ、S3 Compatible Object Storage 和 V1.1 Agent Runtime。数据库以 PostgreSQL 为业务事实源；Redis 用于短期缓存、运行协调和限流，不作为 Agent Version 或审计的唯一存储。

本文件定义新增领域模型和接口方向。实施前需与 V1.0/V1.1 实际 DDL 合并，避免重复创建已有的 users、roles、tools、runs、traces、model_profiles 等实体。

## 2. 数据库新增实体

### 2.1 agents

| 字段 | 类型 | 约束/说明 |
|---|---|---|
| id | uuid | PK |
| agent_key | varchar(100) | 唯一，规范化 |
| name | varchar(200) | NOT NULL |
| description | text | nullable |
| category | varchar(40) | CHECK |
| owner_user_id | uuid | FK 平台用户；V1.0/V1.1 主体先经 Identity 映射 |
| team_id | uuid | nullable |
| visibility | varchar(30) | private/team/organization |
| status | varchar(30) | draft/active/suspended/archived |
| current_version_id | uuid | nullable，仅指当前生产可用版本 |
| lock_version | integer | 乐观锁 |
| created_at / updated_at | timestamptz | NOT NULL |
| archived_at | timestamptz | nullable |

### 2.2 agent_versions

| 字段 | 类型 | 说明 |
|---|---|---|
| id | uuid | PK |
| agent_id | uuid | FK agents |
| version_number | integer | Agent 内递增 |
| status | varchar(30) | draft/validating/ready/published/superseded/rejected |
| schema_version | varchar(30) | Definition Schema |
| definition_json | jsonb | 声明式定义 |
| definition_hash | varchar(128) | 内容 Hash |
| validation_report | jsonb | 结构化验证结果 |
| release_notes | text | nullable |
| created_by | uuid | FK users |
| published_by | uuid | nullable |
| published_at | timestamptz | nullable |
| created_at | timestamptz | NOT NULL |
| based_on_version_id | uuid | nullable |

唯一约束：(agent_id, version_number)。已发布版本禁止 UPDATE definition_json；数据库权限或应用层触发器应共同保护不可变性。

### 2.3 agent_version_bindings

可以存入 definition_json，也可为常用查询建立规范化子表。推荐保留 Definition JSON 为发布快照，同时建立关系表用于资源引用和删除保护：

- id
- agent_version_id
- binding_type：prompt / model_profile / tool / knowledge_base / memory_policy / guardrail_policy
- resource_id
- resource_version_id nullable
- config_snapshot jsonb
- created_at

需建立资源反向引用索引，阻止删除仍被已发布版本引用的资源。

### 2.4 prompts / prompt_versions

prompts：
- id、prompt_key、name、description、owner_id、status、created_at、updated_at

prompt_versions：
- id、prompt_id、version_number、template_body、variables_schema jsonb、content_hash、change_note、created_by、created_at、published_at

### 2.5 agent_permissions

如既有 RBAC 已支持资源级授权，优先复用统一授权表；否则增加：
- id、agent_id、subject_type、subject_id、permission、granted_by、created_at、expires_at

资源 permission 目录：view / edit / test / evaluate / publish / operate / view_trace。回滚/暂停/恢复分别使用 agent.rollback / agent.suspend / agent.resume 的 Policy Action，资源检查统一 operate，并叠加角色、归属、状态与目标版本条件；创建使用组织级创建授权。Owner 不默认获得 publish/operate。完整映射见统一契约第 7 节，禁止以 UI 可见性代替授权。

### 2.6 evaluation_datasets / evaluation_dataset_versions / evaluation_cases

Dataset 元数据与版本分离。Dataset Version 发布后不可修改。Case 内容可存 jsonb，但需校验 schema_version。大体量附件和 Fixture 存对象存储，数据库只存 URI、Hash、类型和权限元数据。

### 2.7 evaluation_profiles / evaluation_profile_versions

保存指标、评分器、阈值、超时、并发、Judge Profile 和硬门禁配置。发布后不可变。

### 2.8 evaluation_runs / evaluation_results

evaluation_runs：
- id、target_type（rag/agent）、target_snapshot jsonb、agent_id、agent_version_id、dataset_version_id、profile_version_id
- RAG-only 的 Agent 字段可空；Agent 评测必须固定非空 Agent Version
- status、initiator_id、queue_job_id、started_at、finished_at
- summary_metrics jsonb、report_object_key、trace_group_id
- error_code、error_summary、created_at

evaluation_results：
- id、evaluation_run_id、case_id、status
- actual_output jsonb、citations jsonb、tool_calls jsonb
- policy_decisions jsonb、metric_scores jsonb、assertion_results jsonb
- latency_ms、input_tokens、output_tokens、estimated_cost
- failure_category、trace_id、created_at

对敏感内容采用独立加密/脱敏策略。大型 Trace 和报告不应无限制塞入 PostgreSQL JSON 字段。

### 2.9 agent_release_events

保存规范结果事件 agent.version.published / agent.version.rolled_back / agent.suspended / agent.resumed；业务 action=publish/rollback/suspend/resume 存 metadata：
- id、agent_id、from_version_id、to_version_id
- event_type、actor_id、reason、gate_report_id
- request_id、created_at、metadata jsonb

### 2.10 agent_audit_events

尽可能复用平台统一操作审计表。若需扩展，采用统一审计 Schema，不另造孤立日志系统。

## 3. 索引与约束

- agents(agent_key) UNIQUE
- agents(owner_user_id, status)
- agents(team_id, status)
- agent_versions(agent_id, version_number) UNIQUE
- agent_versions(agent_id, status, created_at DESC)
- agent_version_bindings(binding_type, resource_id)
- prompts(prompt_key) UNIQUE
- prompt_versions(prompt_id, version_number) UNIQUE
- evaluation_runs(agent_id, created_at DESC)
- evaluation_runs(status, created_at)
- evaluation_results(evaluation_run_id, case_id) UNIQUE
- agent_release_events(agent_id, created_at DESC)

JSONB 字段需对实际查询路径评估 GIN 索引，不要无差别建立大索引。

## 4. API 规范

统一响应结构、分页、错误码、请求 ID、幂等键和鉴权中间件。示例为逻辑 Contract，最终 OpenAPI 需自动生成并纳入 CI Diff。

### 4.1 Agent

- POST /api/v1/agents
- GET /api/v1/agents
- GET /api/v1/agents/{agent_id}
- PATCH /api/v1/agents/{agent_id}
- POST /api/v1/agents/{agent_id}/duplicate
- POST /api/v1/agents/{agent_id}/archive

### 4.2 Version

- POST /api/v1/agents/{agent_id}/versions
- GET /api/v1/agents/{agent_id}/versions
- GET /api/v1/agent-versions/{version_id}
- PATCH /api/v1/agent-versions/{version_id}（仅 Draft）
- POST /api/v1/agent-versions/{version_id}/validate
- POST /api/v1/agent-versions/{version_id}/publish
- POST /api/v1/agents/{agent_id}/rollback
- POST /api/v1/agents/{agent_id}/suspend
- POST /api/v1/agents/{agent_id}/resume

### 4.3 Prompt

- POST /api/v1/prompts
- GET /api/v1/prompts
- POST /api/v1/prompts/{prompt_id}/versions
- GET /api/v1/prompts/{prompt_id}/versions
- POST /api/v1/prompt-versions/{version_id}/render
- GET /api/v1/prompt-versions/{version_id}/diff?base_version_id=

### 4.4 Playground

- POST /api/v1/playground/sessions
- POST /api/v1/playground/sessions/{session_id}/runs
- GET /api/v1/playground/runs/{run_id}
- POST /api/v1/playground/runs/{run_id}/cancel
- GET /api/v1/playground/runs/{run_id}/events（SSE）
- POST /api/v1/playground/runs/{run_id}/retry

Playground API 必须服务端固定 environment=playground，并强制应用 Sandbox Policy；不能由客户端传入 environment=production 来切换。

### 4.5 Evaluation

- POST /api/v1/evaluation/datasets
- POST /api/v1/evaluation/datasets/{id}/versions
- POST /api/v1/evaluation/dataset-versions/{id}/cases:batch
- POST /api/v1/evaluation/runs
- GET /api/v1/evaluation/runs/{run_id}
- GET /api/v1/evaluation/runs/{run_id}/results
- GET /api/v1/evaluation/runs/{run_id}/report
- POST /api/v1/evaluation/runs/{run_id}/cancel
- POST /api/v1/evaluation/compare

### 4.6 Release

回滚写接口统一定义于 4.2 Version，本节仅列发布记录与 Gate 查询。

- GET /api/v1/agents/{agent_id}/releases
- GET /api/v1/agents/{agent_id}/release-gates

## 5. 核心 Contract

### 5.1 AgentDefinition Contract

- schema_version 必填。
- 未知字段默认拒绝或按显式兼容策略处理。
- 对枚举、数值范围、引用 ID、数组大小和嵌套深度设上限。
- Definition JSON 不能包含密钥、任意 URL 执行指令或代码片段。
- API 接收后先做 Schema Validation，再做资源级授权与业务验证。

### 5.2 Agent Run Contract

每次 Run 固定：
- agent_id
- agent_version_id
- environment
- caller_identity / delegated_identity
- conversation_id
- run_id
- policy_context
- budget_context
- trace_context

运行中不可由客户端修改 Agent Version 或提升权限。Run 的最终授权由 Policy Engine 计算。

### 5.3 Evaluation Contract

Evaluation Job 至少固定：
- Agent Version
- Dataset Version
- Evaluation Profile Version
- Model Profile Snapshot / provider deployment reference
- Tool Fixture Set
- Runner Version
- Judge Version

报告必须暴露影响可比性的配置差异。

### 5.4 Event Contract

关键事件：
- agent.version.validated
- agent.version.published
- agent.version.rolled_back
- agent.suspended
- agent.resumed
- evaluation.run.queued
- evaluation.run.started
- evaluation.case.completed
- evaluation.run.completed
- evaluation.run.failed
- evaluation.run.cancelled

事件包含 event_id、event_type、schema_version、occurred_at、aggregate_id、correlation_id、payload。发布记录 action、审计动作与集成事件按统一契约字典映射，审计可包含更多管理行为。旧 agent.version.rollback 仅作接收兼容别名，转换后保留 event_id 去重，不双发两种事件。消费者需幂等。

## 6. 安全与隔离

- 每个 API 执行身份认证、RBAC、资源 ACL 和组织范围校验。
- Definition 引用资源时校验用户可配置权限；运行时再次执行资源授权。
- Playground 的 Sandbox Policy 在服务端强制注入。
- Model / Tool 凭证仅由 Gateway 解析，客户端和 Definition 不接触。
- Evaluation Job 使用独立服务身份和受限资源授权。
- Trace、Dataset、Result 的访问遵循既有隐私策略。
- 对发布、回滚、权限变更和高风险绑定写不可删除审计事件。

## 7. 迁移策略

1. Alembic Migration 采用向前兼容的 Expand-Contract。
2. 新增列先 nullable / default-safe，再部署兼容代码，最后收紧约束。
3. Agent Definition Schema 迁移必须可重复、可测试；保留原始 Schema Version 和迁移记录。
4. 历史 Agent Version 不做静默重写。
5. API 至少保持一个兼容窗口；弃用字段先告警、后移除。
6. 数据库回滚不能依赖破坏性 downgrade；生产回滚优先通过应用版本回滚和兼容迁移。
7. 按统一契约第 3/4/6 节回填旧 Agent Definition、Run 版本和 eval_* 数据；保留来源 ID/配置 Hash，不静默改变历史快照，旧注册/API 入口经 Adapter 继续使用同一事实源。

## 8. Contract 测试与验收

- OpenAPI Schema Snapshot / Diff。
- JSON Schema 正反例测试。
- API 权限矩阵测试。
- 幂等键和并发发布测试。
- Event Consumer 重复投递测试。
- Definition Version Migration 测试。
- 数据库迁移升级测试和兼容性测试。
- 发布后不可变性测试。
- Playground 强制 Sandbox 测试。
