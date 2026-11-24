# V1.3-06 数据库、API Contract 与代码结构设计

> 公共字段、状态、事件、权限与迁移映射见 [统一契约与跨版本演进规则](../../architecture/统一契约与跨版本演进规则.md)；本文件描述本版能力及增量，具体实现须通过契约与升级验收。

## 1. 设计原则

沿用 V1.0 PostgreSQL、Redis、Object Storage、RabbitMQ/Celery、Elasticsearch、OpenTelemetry 基线。V1.3 不引入新的主数据库，不让 Agent Runtime 直接访问 Search Backend。所有关键状态可持久化、可恢复、可审计。

## 2. 核心数据表

### 2.1 agent_runs：在 V1.1 基线上增量扩展

保留 V1.1 的 id、agent_key、config_version、conversation_id、requester_subject_id、status、idempotency_key、trace_id、input_ref/output_ref、budget_json、started_at/finished_at、error_code、created_at/updated_at；字段类型和幂等唯一键见统一契约第 4 节。principal_ref 是脱敏视图，不替换授权主体列。

V1.2 已新增 agent_id / agent_version_id，存量快照经 Registry 映射回填，新生产 Run 固定发布版本。本版新增：
- goal_summary
- execution_phase / waiting_reason
- deadline_at / cancel_requested_at
- total_steps
- token_usage_json / cost_estimate
- error_summary
- original_run_id（终态纠错新 Run 的来源引用）

消耗字段不替代预算上限；外部 completed_at/token_usage 需要时通过兼容 DTO 映射到 finished_at/token_usage_json。不得直接删列、改名或另建平行 agent_runs。

### 2.2 agent_plans
- id
- run_id
- revision
- status
- planner_model_id
- plan_json
- validation_result
- revision_reason
- created_at

唯一约束：`(run_id, revision)`。

### 2.3 agent_tasks
- id
- run_id
- plan_id
- task_key
- task_type
- description
- dependencies_json
- assigned_agent_version_id
- status
- input_ref
- output_ref
- risk_level
- retry_count
- started_at / finished_at

唯一约束：`(plan_id, task_key)`。

### 2.4 agent_steps：保留序号与用量字段

保留 V1.1 的 id、run_id、sequence_no、node_key、step_type、status、attempt、input_summary/output_summary、error_code、latency_ms、token_usage_json、started_at/finished_at。本版新增 task_id（旧 Step 可空）、capability_ref、input_hash、output_ref、idempotency_key、cost_estimate。

`(run_id, sequence_no)` 保持唯一；Task 内展示序号可派生，但不能用重复的 step_index 替换全 Run 的单调序号。Step/Tool 去重不替代 Run 创建幂等。

### 2.5 agent_checkpoints：保留版本与 TTL

保留 id、run_id、checkpoint_seq、schema_version、checkpoint_ref、agent_config_version、created_at、expires_at、deleted_at；V1.2 增加 agent_version_id，本版新增 state_hash / status。state_ref 是 Checkpoint Adapter 内部名称，不直接替换持久化 checkpoint_ref。

恢复校验原配置及发布快照、当前授权、Hash、有效期和剩余预算；新清单不取消 V1.1 的清理与生命周期规则。

### 2.6 agent_events
- id
- run_id
- sequence_no
- event_type
- schema_version
- payload_json
- created_at

唯一约束：`(run_id, sequence_no)`；按 Run 分页读取。

### 2.7 agent_handoffs
- id
- parent_run_id
- child_run_id
- parent_task_id
- worker_agent_id
- worker_version_id
- delegated_capabilities_json
- status
- created_at / finished_at

### 2.8 human_interactions
- id（interaction_type=approval 时即 approval_id）
- run_id / step_id
- interaction_type
- requested_action_json / target_resource
- input_summary / risk_level / policy_decision_ref
- parameter_hash / required_role
- idempotency_key
- status（审批请求初始 pending；结果 approved/rejected/expired/cancelled）
- expires_at
- decision_id / decision
- decided_by / decision_reason / decided_at

语义采用统一 ApprovalRequest/ApprovalDecision；请求与决定分离，保存同表结果列及追加审计。旧 approval-result 回调适配到同一决定服务，澄清/复核不签发动作审批 Token。

### 2.9 agent_artifacts
- id
- run_id
- artifact_type
- storage_uri
- content_hash
- metadata_json
- access_scope
- created_at
- expires_at

### 2.10 evaluation 扩展
复用 V1.2 Evaluation Dataset / Run / Result 结构，新增：
- plan_metrics_json
- execution_metrics_json
- evidence_metrics_json
- collaboration_metrics_json
- safety_metrics_json
- cost_metrics_json

## 3. 索引与数据约束

- `agent_runs(status, created_at)` 用于运行列表和运维。
- `agent_runs(agent_id, agent_version_id, created_at)` 用于版本分析。
- `agent_tasks(run_id, status)`、`agent_steps(run_id, task_id)`。
- `agent_events(run_id, sequence_no)`。
- `human_interactions(status, expires_at)`。
- JSON 字段仅存结构化小对象；大内容写 Object Storage。
- 对事件和 Trace 设保留策略；会话与身份映射遵循既有生命周期规则。
- 所有用户可见查询都按 Principal / ACL 过滤。

## 4. API 设计

### 4.1 创建与运行
`POST /api/v1/agent-runs`
```json
{
  "agent_id": "agent_x",
  "agent_version": "published",
  "conversation_id": "conv_x",
  "input": {"message": "请比较这些政策并给出差异"},
  "execution_mode": "auto"
}
```
返回 `run_id`、公共 status、可选 execution_phase 和 Trace ID。Idempotency-Key 由客户端或网关首次提供，重试复用同一 Key；同 Key 不同输入/版本返回冲突。旧 POST /api/v1/agents/{agent_key}/runs 保留 Key Resolver Adapter，两个入口共享同一 Run Service、主体授权和数据库幂等约束。

`agent_version=published` 的重试先查询去重记录，复用第一次解析的快照；不能因发布指针变化而创建新 Run 或重新绑定版本。显式改输入/目标版本使用新 Key。

### 4.2 查询运行
- `GET /api/v1/agent-runs/{run_id}`
- `GET /api/v1/agent-runs/{run_id}/plans`
- `GET /api/v1/agent-runs/{run_id}/tasks`
- `GET /api/v1/agent-runs/{run_id}/steps`
- `GET /api/v1/agent-runs/{run_id}/events?after_seq=123`（显式 Accept: application/json 分页补拉；默认保留 V1.1 SSE 行为）
- `GET /api/v1/agent-runs/{run_id}/artifacts`

### 4.3 控制运行
- `POST /api/v1/agent-runs/{run_id}/cancel`
- `POST /api/v1/agent-runs/{run_id}/pause`
- `POST /api/v1/agent-runs/{run_id}/resume`（需权限和状态校验）
- `POST /api/v1/agent-runs/{run_id}/clarifications`
- `POST /api/v1/human-interactions/{interaction_id}/decision`

### 4.4 SSE 事件
`GET /api/v1/agent-runs/{run_id}/stream`
- 支持 `Last-Event-ID` 或序号游标。
- SSE 仅负责传输，事件持久化以数据库为准。
- 客户端断线可通过 events API 补齐。

### 4.5 API 安全
- 所有接口校验 Run 所属主体、Agent 访问权和当前资源权限。
- `run_id` 不构成访问授权。
- Approval Decision 需验证角色、审批范围和参数 Hash。
- 限制请求体大小、事件读取范围和并发连接。

## 5. 内部 Contract

### Planner
`create_plan(context, capabilities, budget) -> Plan`

### PlanValidator
`validate(plan, definition_snapshot, policy_context) -> ValidationResult`

### Executor
`execute(plan, run_context) -> ExecutionResult`

### CheckpointStore
`save(run_state) -> CheckpointRef`
`restore(checkpoint_ref) -> RunState`

### DelegationService
`delegate(task, worker_version, capability_scope) -> ChildRunRef`

### EvidenceService
`collect(query) -> EvidenceSet`
`verify(claims, evidence_set) -> VerificationResult`

### HumanInteractionService
`request(interaction) -> InteractionRef`
`resolve(interaction_id, decision) -> DecisionResult`

所有接口使用平台领域模型，不直接暴露 LangGraph State 或 LlamaIndex 内部类型。框架对象只能存在 Adapter 层。

## 6. 推荐代码结构

```text
backend/
  app/
    api/
      agent_runs.py
      agent_events.py
      human_interactions.py
    domain/
      agent_run/
      planning/
      execution/
      delegation/
      evidence/
      approval/
      evaluation/
    application/
      run_service.py
      planning_service.py
      execution_service.py
      recovery_service.py
      delegation_service.py
    infrastructure/
      persistence/
      checkpoint/
      event_bus/
      object_storage/
      model_gateway/
      tool_gateway/
      retriever/
      observability/
    adapters/
      langgraph/
      llamaindex/
    workers/
      run_worker.py
      timeout_worker.py
      approval_expiry_worker.py
  tests/
    unit/
    integration/
    contract/
    evaluation/
    security/
```

## 7. 事务与一致性

- 创建 Run 与初始事件采用同一数据库事务。
- 任务派发采用 Outbox Pattern，避免 DB 提交成功但消息未发布。
- 消费者以 Event ID / Idempotency Key 去重。
- Step 状态变更和事件写入同事务提交。
- 外部 Tool 副作用不能依赖数据库事务回滚；必须使用幂等键和显式结果确认。
- Checkpoint 和 Artifact 使用内容 Hash 校验。

## 8. 迁移策略

- 只为 Plan/Task/Handoff/HumanInteraction/Artifact 等新增实体建立独立 Migration；Run/Step/Checkpoint 依统一契约增量加列，保留旧字段、唯一约束、TTL 和配置映射。
- Agent Definition 增加可选字段并设置安全默认值。
- V1.2 旧 Agent 可继续运行单 Agent 模式。
- 发布快照需记录 Schema Version。
- API 采用 `/api/v1`，事件 payload 单独版本化；数据库 sequence_no→SSE sequence、内部 state_ref→checkpoint_ref、Trace principal_ref→受控匿名视图采用显式映射。
- 升级验证旧 Run 幂等键、快照、预算、Step 序号和 Checkpoint 有效期；旧创建/SSE/审批回调入口继续使用同一事实源。

## 9. 验收标准

- API Contract 有 OpenAPI 和契约测试。
- 幂等、Outbox、事件序号和断线补拉有效。
- Checkpoint 恢复能通过集成测试。
- 数据权限与 Run 主体绑定。
- V1.2 已发布 Agent 在默认配置下保持兼容。
