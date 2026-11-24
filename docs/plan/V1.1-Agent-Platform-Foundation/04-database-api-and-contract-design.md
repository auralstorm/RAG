# 04｜V1.1 数据库、API 与核心 Contract 设计

> 公共字段、状态、事件、权限与迁移映射见 [统一契约与跨版本演进规则](../../architecture/统一契约与跨版本演进规则.md)；本文件描述本版能力及增量，具体实现须通过契约与升级验收。

**版本：** V1.1 — Agent Platform Foundation  
**状态：** 研发设计基线  
**兼容原则：** 在 V1.0 业务模型上增量演进，不破坏现有 Chat、RAG、KB、用户权限和审计链路。

---

## 1. 设计原则

1. PostgreSQL 是 Agent Run、Tool Call、Memory 元数据和业务状态的事实来源。
2. Redis 用于短期缓存、限流和租约辅助，不作为唯一运行状态存储。
3. RabbitMQ 传递异步执行任务和事件，不作为唯一任务记录。
4. LangGraph State、LlamaIndex Node、MCP SDK 对象不得直接成为数据库公共结构。
5. 每个核心对象具备稳定 ID、状态、版本、创建/更新时间和审计关联。
6. 数据库迁移采用 Expand-Migrate-Contract。
7. 所有 API 统一错误结构、分页、认证、权限、Request ID 和 Trace ID。

## 2. V1.1 新增实体

### 2.1 agent_definitions

| 字段 | 类型 | 说明 |
|---|---|---|
| id | UUID | 主键 |
| agent_key | VARCHAR | 稳定业务标识，唯一 |
| name | VARCHAR | 名称 |
| description | TEXT | 描述 |
| status | VARCHAR | ACTIVE / DISABLED |
| config_version | VARCHAR | 配置快照版本 |
| config_json | JSONB | 受控配置，不含 Secret |
| owner_subject_id | UUID | 所有者 |
| created_at/updated_at | TIMESTAMPTZ | 时间 |

V1.1 可由代码/受控配置写入，后台完整管理界面留给 V1.2。

### 2.2 agent_runs

核心字段：
- `id UUID PRIMARY KEY`
- `agent_key`
- `config_version`
- `conversation_id NULL`
- `requester_subject_id`
- `status`
- `idempotency_key`
- `trace_id`
- `input_ref` / `output_ref`
- `budget_json`
- `started_at` / `finished_at`
- `error_code`
- `created_at` / `updated_at`

创建 Run 的三列必须非空，数据库唯一键为 `(requester_subject_id, agent_key, idempotency_key)`。同 Key 相同请求返回原 Run，不同请求摘要返回冲突；Run 存续期间保留去重键，清理后的去重窗口由部署配置明确。V1.2 增加实体/版本 ID，V1.3 只增量扩展，不删除本节字段；预算上限不能由 Token/成本消耗字段替代。

### 2.3 agent_steps

- `id`
- `run_id`
- `sequence_no`
- `node_key`
- `step_type`
- `status`
- `attempt`
- `input_summary`
- `output_summary`
- `error_code`
- `latency_ms`
- `token_usage_json`
- `started_at` / `finished_at`

索引：`(run_id, sequence_no)` 唯一；`(run_id, status)`。

### 2.4 agent_checkpoints

- `id`
- `run_id`
- `checkpoint_seq`
- `schema_version`
- `checkpoint_ref` 或受控结构化内容
- `agent_config_version`（与原 config_version 一致，后续增加 agent_version_id 不覆盖原值）
- `created_at`
- `expires_at`
- `deleted_at`

大体积 Checkpoint 建议存储于专用受控存储，数据库仅保存引用和元数据；不得存储 Secret。

### 2.5 tools / tool_versions

`tools` 保存稳定业务标识和启停状态；`tool_versions` 保存不可变 Schema、风险等级、Effect、超时、重试策略和 Connector 绑定快照。

### 2.6 connectors / connector_instances

- Connector 类型和 Adapter Key；
- Connector Instance 的环境、Endpoint Reference、Secret Reference；
- 健康状态、最近检查时间；
- 配置版本；
- 不保存明文 Secret。

### 2.7 tool_calls

- `id`
- `run_id`
- `agent_step_id`
- `tool_key`
- `tool_version`
- `connector_instance_id`
- `status`
- `policy_decision_id`
- `arguments_summary`
- `result_summary`
- `idempotency_key_hash`
- `error_code`
- `latency_ms`
- `trace_id`
- `created_at` / `finished_at`

### 2.8 memory_artifacts

记录 Summary、Task Memory、Checkpoint 等的统一元数据与引用：
- `id`
- `memory_type`
- `owner_subject_id`
- `conversation_id`
- `run_id`
- `content_ref`
- `source_refs_json`
- `schema_version`
- `sensitivity_level`
- `expires_at`
- `deleted_at`

### 2.9 policy_decisions

若 V1.0 已有统一审计/策略表，优先扩展而非重复建表。至少保留：
- Subject、Action、Resource、Decision、Reason Code；
- Policy Version；
- Request/Trace ID；
- 时间和执行点。

## 3. 状态枚举

### Agent Run
`QUEUED, ACCEPTED, RUNNING, WAITING_APPROVAL, WAITING_INPUT, CANCEL_REQUESTED, SUCCEEDED, FAILED, CANCELLED, TIMED_OUT`

### Agent Step
`PENDING, RUNNING, SUCCEEDED, FAILED, SKIPPED, CANCELLED`

### Tool Call
`PENDING, VALIDATING, DENIED, RUNNING, SUCCEEDED, FAILED, TIMED_OUT, CANCELLED, UNKNOWN`

### Connector
`CONFIGURED, HEALTHY, DEGRADED, UNAVAILABLE, DISABLED`

枚举新增必须兼容旧消费者；未知状态应安全降级为不可执行状态。

## 4. API 规范

统一响应：
```json
{
  "data": {},
  "meta": {
    "request_id": "req_x",
    "trace_id": "trace_x"
  },
  "error": null
}
```

错误响应：
```json
{
  "data": null,
  "meta": {"request_id": "req_x", "trace_id": "trace_x"},
  "error": {
    "code": "AGENT_RUN_FORBIDDEN",
    "message": "The requested operation is not permitted",
    "retryable": false
  }
}
```

### Agent Run APIs
- `POST /api/v1/agents/{agent_key}/runs`
- `GET /api/v1/agent-runs/{run_id}`
- `GET /api/v1/agent-runs/{run_id}/events`（SSE）
- `GET /api/v1/agent-runs/{run_id}/steps`
- `POST /api/v1/agent-runs/{run_id}/cancel`
- `POST /api/v1/agent-runs/{run_id}/resume`
- `POST /api/v1/agent-runs/{run_id}/approval-result`（内部适配回调，进入统一审批决定服务）

创建请求建议：
```json
{
  "conversation_id": "uuid",
  "input": {"message": "请查询模拟员工信息"},
  "response_mode": "stream",
  "client_request_id": "client-generated-id"
}
```

客户端不得传入可覆盖的 `requester_subject_id`、权限列表、Policy Decision 或 Secret。

### Tool Catalog APIs
- `GET /api/v1/tools`
- `GET /api/v1/tools/{tool_key}`
- `GET /api/v1/tool-calls/{tool_call_id}`

### Connector Admin APIs
- `GET /api/v1/connectors`
- `POST /api/v1/connectors`（管理员）
- `PATCH /api/v1/connectors/{id}`（管理员）
- `POST /api/v1/connectors/{id}/health-check`（管理员）

### Memory APIs
- `GET /api/v1/conversations/{id}/context-status`
- `GET /api/v1/agent-runs/{run_id}/budget`
- 内部摘要与 Checkpoint API 不向普通客户端开放。

## 5. SSE 事件 Contract

事件统一包含：
- `event_id`
- `run_id`
- `sequence`
- `event_type`
- `occurred_at`
- `payload`
- `schema_version`

事件类型建议：
- `run.accepted`
- `run.started`
- `step.started`
- `step.completed`
- `tool.started`
- `tool.completed`
- `run.waiting_approval`
- `run.waiting_input`
- `run.completed`
- `run.failed`
- `run.cancelled`

SSE 断线重连使用 Last-Event-ID 或等价序列游标；事件必须可重放或明确告知客户端状态需重新拉取。

## 6. 异步任务事件

RabbitMQ 消息只传必要引用：
```json
{
  "event_id": "uuid",
  "event_type": "agent.run.execute",
  "schema_version": "1",
  "run_id": "uuid",
  "trace_id": "trace-id",
  "occurred_at": "ISO-8601"
}
```

要求：
- 消费者幂等；
- Run 状态先持久化再发消息，建议 Outbox；
- 重复消息不重复启动终态 Run；
- 失败重试有上限和 Dead Letter Queue；
- 任务 payload 不携带 Secret 和大段个人数据。

## 7. Policy Contract

统一输入：
- `subject`
- `actor`（Agent/Service Identity）
- `action`
- `resource`
- `context`（企业内资源/组织范围、environment、purpose、risk）
- `trace_id`

输出：
- `decision`: ALLOW / DENY / REQUIRE_APPROVAL
- `reason_code`
- `policy_version`
- `decision_id`
- `obligations`（如字段脱敏、行数限制）

V1.1 重点增加 `tool.invoke`、`agent.run`、`connector.use` 动作类型。Policy Engine 是服务端最终决策点。

## 8. 数据库迁移策略

1. 新增表和可空字段；
2. 部署兼容代码；
3. 执行数据回填（如有）；
4. 校验行数、唯一约束和引用完整性；
5. 切换读写路径；
6. 观察一个发布窗口；
7. 再考虑删除旧字段或旧逻辑。

所有迁移脚本必须支持从当前 V1.0 数据库升级，不得要求清空业务数据。

## 9. API 安全要求

- 用户 API 与 Runtime 内部 API 分离；
- Runtime Service 使用服务身份认证；
- 用户身份从可信认证层注入；
- 所有 Run/Tool Call 查询按主体和授权范围过滤；
- SSE 连接必须持续校验资源归属；
- 不向普通用户返回内部 Prompt、完整 Tool 参数、Secret、原始 Checkpoint；
- 管理接口必须 RBAC + 审计；
- Rate Limit 与 Budget Limit 同时生效。

## 10. Contract 测试

- OpenAPI Schema 兼容测试；
- API 错误码测试；
- SSE 事件顺序、重连和重复事件测试；
- Tool Contract 输入/输出 Schema 测试；
- Policy Request/Decision Contract 测试；
- RabbitMQ Event Schema 测试；
- 数据库迁移升级测试；
- V1.0 Chat/RAG 回归测试；
- 未知字段/未知枚举值兼容测试。

## 11. 验收标准

- V1.0 数据库可无损升级到 V1.1；
- Agent Run/Step/Tool Call 状态持久化完整；
- API Contract 不暴露框架内部对象；
- SSE 支持重连或可靠状态回查；
- Policy Decision 可追踪；
- 消息重复投递不会重复创建执行；
- 所有管理接口和高风险动作写审计；
- 迁移和回滚方案经过演练。

## 12. 审批与后续版本兼容

WAITING_APPROVAL 对应 ApprovalRequest 的 pending 状态；ApprovalDecision 与执行结果分离。最小字段、参数 Hash、角色校验、过期/重放规则采用统一契约第 5 节，V1.1 用受控 Mock 或可信外部审批方验收。V1.3 human_interactions 承接相同 approval_id，旧回调保留适配窗口，V1.4 增加企业审批流程实体而不是另建审批 ID 空间。

V1.2/V1.3 的 Run/Step/Checkpoint 使用本版表为基线，保留 sequence_no、finished_at、配置版本和 TTL；公共 status 与高级 execution_phase 分离。数据库、SSE 和 Trace 的字段映射及旧入口兼容见统一契约规则。
