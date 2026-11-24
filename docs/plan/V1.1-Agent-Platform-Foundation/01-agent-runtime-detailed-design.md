# 01｜Agent Runtime 详细技术设计

> 公共字段、状态、事件、权限与迁移映射见 [统一契约与跨版本演进规则](../../architecture/统一契约与跨版本演进规则.md)；本文件描述本版能力及增量，具体实现须通过契约与升级验收。

**项目：** Enterprise Agentic AI Platform  
**版本：** V1.1 — Agent Platform Foundation  
**状态：** 研发设计基线（待架构评审与 POC 验收）  
**技术基线：** Python + FastAPI + LangGraph + PostgreSQL + Redis + RabbitMQ/Celery + Model Gateway

---

## 1. 文档目的与范围

本文定义 V1.1 单 Agent Runtime 的架构、运行模型、状态管理、执行生命周期、错误处理、Checkpoint、并发控制和可观测要求。

V1.1 的目标是建立安全、可恢复、可观测的 Agent 执行底座，而不是建设完整 Agent Builder 或 Multi-Agent 平台。

### 1.1 本版本实现

- 基于 LangGraph 构建单 Agent 执行适配层。
- 统一 Agent Run、Step、State、Checkpoint 和事件模型。
- Agent 可调用平台 Retriever API 和 Tool Gateway。
- 支持同步短任务和异步长任务的基础运行模式。
- 支持超时、取消、有限重试、最大步数、Token/成本预算。
- 支持执行状态查询、Checkpoint 恢复、Trace 关联和审计。
- 支持人工审批的基础暂停/恢复协议，但不建设完整 Approval Center。

### 1.2 本版本不实现

- 可视化拖拽式 Agent Builder、Agent Registry 完整管理界面（V1.2）。
- Planner 驱动的复杂任务拆解、Multi-Agent Supervisor（V1.3）。
- 企业级 Workflow Engine 和业务审批流程（V1.4）。
- 任意 Python 代码沙箱执行、任意 Shell、任意 URL 访问。
- Agent 自行修改权限、策略、模型凭据或 Tool 授权。
- 将 LangGraph 内部 State 直接作为平台永久数据契约。

## 2. 架构定位

```text
Chat / Application API
        |
        v
Agent Application Service
        |
        +---- Identity Context
        +---- Policy Engine
        +---- Budget / Rate Limit
        |
        v
Agent Runtime Adapter
        |
        +---- LangGraph Compiled Graph
        |       +-- Input / Context Node
        |       +-- Model Node (Model Gateway)
        |       +-- Tool Dispatch Node (Tool Gateway)
        |       +-- RAG Retriever Node (Retriever API)
        |       +-- Output / Finalize Node
        |
        +---- Checkpoint Adapter
        +---- Event Publisher
        +---- Trace Adapter
        |
        v
PostgreSQL / Redis / RabbitMQ / Phoenix
```

Runtime 只负责编排 Agent 内部执行。知识检索通过 RAG Engine 的 Retriever Contract；工具调用通过 Tool Gateway；模型调用通过 Model Gateway。

## 3. 核心领域模型

### 3.1 Agent Definition（V1.1 受控定义）

此定义是 V1.2 Registry/Definition 的迁移源；代码注册入口作为 Registry Adapter 复用，字段与 Tool Key/版本映射见统一契约规则。旧 config_version 和授权范围在转换时保持，不新建平行生产 Allowlist。

V1.1 先以代码注册或受控配置定义 Agent，不提供任意用户脚本执行。

字段建议：
- `agent_key`：稳定业务标识。
- `name`、`description`。
- `instruction_ref`：系统指令或 Prompt 模板引用。
- `model_profile_id`：平台模型配置引用。
- `retriever_profile_id`：可选 Retriever 配置引用。
- `allowed_tool_keys`：允许使用的 Tool 白名单。
- `max_steps`、`timeout_seconds`。
- `max_input_tokens`、`max_output_tokens`、`max_total_tokens`。
- `max_cost`（若当前成本计量可用）。
- `config_version`：不可变配置快照版本。
- `status`：ACTIVE / DISABLED。

### 3.2 Agent Run

一次用户触发的 Agent 执行实例。

| 字段 | 说明 |
|---|---|
| run_id | UUID/ULID，唯一运行 ID |
| agent_key | Agent 标识 |
| config_version | 运行时绑定的配置版本 |
| conversation_id | 可选会话关联 |
| requester_subject | 内部主体 ID，不直接暴露给模型 |
| org_scope | 企业内组织/资源授权范围，由可信身份与当前 Policy 计算 |
| status | 生命周期状态 |
| input_ref | 输入数据或脱敏摘要引用 |
| output_ref | 最终输出引用 |
| trace_id | OpenTelemetry Trace |
| idempotency_key | 防止客户端重复提交 |
| started_at / finished_at | 时间戳 |
| error_code | 稳定错误码 |

### 3.3 Agent Step

每个节点/动作的可审计运行单元：
- `step_id`、`run_id`、`sequence_no`；
- `node_key`、`step_type`；
- `status`、`started_at`、`finished_at`；
- `input_summary`、`output_summary`（脱敏）；
- `attempt`、`error_code`；
- `model_request_id`、`tool_call_id`、`retrieval_id`；
- `token_usage`、`latency_ms`。

不得默认将完整敏感输入输出写入普通 Trace。原始内容如确需保留，必须有明确目的、访问控制和生命周期。

## 4. Agent Run 状态机

```text
QUEUED -> ACCEPTED -> RUNNING -> SUCCEEDED
                         |  | \
                         |  |  -> FAILED
                         |  -> WAITING_APPROVAL -> RUNNING
                         |  -> WAITING_INPUT -> RUNNING
                         |  -> CANCEL_REQUESTED -> CANCELLED
                         -> TIMED_OUT
```

补充规则：
- `QUEUED`：已持久化，等待 Worker。
- `ACCEPTED`：Worker 获得执行租约。
- `RUNNING`：图正在执行。
- `WAITING_APPROVAL`：执行被安全暂停，等待外部审批结果。
- `WAITING_INPUT`：需要用户补充输入。
- `CANCEL_REQUESTED`：已请求取消，等待运行节点安全退出。
- `SUCCEEDED/FAILED/CANCELLED/TIMED_OUT`：终态，不允许直接恢复执行。
- 终态纠错通过新 Run 完成，不篡改历史结果。

状态迁移必须由领域服务校验，不能由模型或客户端任意提交。

## 5. 运行流程

1. API 验证身份、请求格式、Agent 状态和调用权限。
2. Policy Engine 校验主体是否可运行该 Agent。
3. 创建 Agent Run，保存配置快照引用、预算、幂等键和 Trace Context。
4. 短任务可由 API 内受控执行；超过阈值的任务进入 RabbitMQ，由 Agent Worker 执行。
5. Runtime 构建 LangGraph 输入，将可信身份上下文作为不可由模型覆盖的运行上下文。
6. Model Node 通过 Model Gateway 调用模型。
7. Tool Dispatch Node 只能提交 Tool Gateway，不允许直接执行外部 I/O。
8. Retriever Node 调用统一 Retriever API。
9. 每个节点开始/完成/失败时写运行事件和 Trace Span。
10. 运行成功后校验输出、写入结果并更新终态。
11. 失败时按错误分类决定重试、暂停或终止。

## 6. LangGraph Adapter 设计

### 6.1 适配原则

- LangGraph 仅是 Runtime 实现，不是平台领域模型。
- 通过 `AgentGraphFactory` 将 Agent Definition 转为 Graph。
- 通过 `CheckpointStoreAdapter` 适配持久化。
- 通过 `ToolNodeAdapter` 统一调用 Tool Gateway。
- 通过 `ModelNodeAdapter` 统一调用 Model Gateway。
- 通过 `RetrieverNodeAdapter` 调用 RAG Retriever API。
- 通过 `RuntimeEventAdapter` 将图执行事件转成平台事件。

### 6.2 State 设计

State 仅保存执行所需的最小结构：
- `run_id`、`conversation_id`；
- `messages` 或 message references；
- `plan_context`（V1.1 只允许简单步骤/当前节点，不实现复杂 Planner）；
- `retrieval_refs`；
- `tool_call_refs`；
- `budget_state`；
- `current_status`；
- `final_answer_ref`。

敏感身份字段不应放入可被 LLM 读写的 Message State；可信上下文应在服务端执行层单独持有。

### 6.3 Checkpoint

Checkpoint 必须：
- 与 `run_id` 和 checkpoint sequence 关联；
- 具备 schema version；
- 保存恢复所需状态，不保存不必要的 Secret；
- 具备保留期限和删除机制；
- 只能由 Runtime 服务读写；
- 恢复前校验 Agent Config Version、Tool Schema Version 和策略版本是否仍可用。

配置变化时不应静默将旧 Run 绑定到新配置。恢复策略：
1. 默认按原配置快照恢复；
2. 原配置/工具版本不可用时暂停并要求人工处理；
3. 不允许自动升级配置后继续执行具有副作用的步骤。

## 7. Tool Calling 与安全边界

- Agent 只能看到当前 Run 被授权的 Tool 列表。
- Tool 白名单是配置约束，Policy Engine 是最终授权判断。
- 每次 Tool Call 都重新执行权限检查，不能只在 Run 开始时检查一次。
- Tool 参数先做 JSON Schema 校验，再做业务级校验。
- 对有副作用的 Tool，必须使用幂等键和操作记录；V1.1 默认只开放 Mock 或只读工具。
- Tool 返回结果要做敏感字段过滤，不能将系统凭据、内部 Token 或不必要字段返回模型。
- Prompt 中的“允许调用”不构成授权。

## 8. Context 与 Budget

每个 Run 建立独立预算：
- 最大执行步数；
- 最大总运行时长；
- 单次模型超时；
- 总 Token 预算；
- 单工具超时；
- 最大 Tool Call 数；
- 可选成本预算。

超预算时返回稳定错误码并终止或等待人工确认。不得通过无限重试绕过预算。

上下文管理：
- 将历史对话按 Token 预算裁剪或摘要；
- 优先保留系统指令、当前用户目标、必要证据和最近交互；
- 旧消息可使用摘要/引用，不应无限追加；
- RAG Evidence 应保留来源引用，不要只保留模型生成摘要而丢失证据链。

## 9. 并发、队列与资源隔离

- Agent Worker 与 Ingestion Worker 分离部署或至少分队列、分并发池。
- 按 Agent、用户主体、模型、Tool 和全局维度配置并发上限。
- 使用 Redis 进行短期分布式限流/租约辅助；PostgreSQL 是 Run 状态事实来源。
- RabbitMQ 消息只传 Run ID 和必要路由信息，不传 Secret 或大段敏感上下文。
- Worker 使用租约/心跳；租约过期后由恢复调度器判断是否可恢复。
- 重复消息必须幂等处理。
- 对慢模型和慢工具设置隔离舱/并发上限，避免耗尽全部 Worker。

## 10. 错误分类与重试

| 错误类型 | 默认策略 |
|---|---|
| 输入 Schema 错误 | 不重试，400 |
| Agent 无权限 | 不重试，403 |
| Agent 禁用 | 不重试，409 |
| 模型限流/临时网络错误 | 有上限指数退避 |
| 模型认证失败 | 不自动无限重试，告警 |
| Tool 参数错误 | 不重试或仅允许受控修正一次 |
| Tool 权限拒绝 | 不重试 |
| Tool 临时错误 | 仅对幂等/只读 Tool 有限重试 |
| Checkpoint 不兼容 | 暂停/失败，人工处理 |
| 超预算/超时 | 终止，不重试 |
| 用户取消 | 传播取消信号并进入 CANCELLED |

所有重试需有 `attempt`、原因、间隔和最终结果记录。

## 11. API Contract（建议）

- `POST /api/v1/agents/{agent_key}/runs`：创建运行。
- `GET /api/v1/agent-runs/{run_id}`：查询运行状态和安全摘要。
- `GET /api/v1/agent-runs/{run_id}/events`：SSE 运行事件。
- `POST /api/v1/agent-runs/{run_id}/cancel`：请求取消。
- `POST /api/v1/agent-runs/{run_id}/resume`：恢复等待中的 Run（仅适用状态）。
- `POST /api/v1/agent-runs/{run_id}/approval-result`：内部审批回调接口，不开放给普通用户直接调用。

所有接口需统一认证、授权、限流、错误码、Request ID 和 Trace ID。

## 12. Observability

Span 建议：
- `agent.run`
- `agent.node`
- `agent.model_call`
- `agent.tool_dispatch`
- `agent.retriever_call`
- `agent.checkpoint.save/load`

属性使用低敏感标签：agent_key、config_version、run_status、node_key、tool_key、model_key、latency、token usage。用户身份默认匿名化。高危溯源沿用平台既有授权和审计规则。

## 13. 测试策略

- Graph Factory 单元测试；
- State Schema 序列化/反序列化测试；
- Checkpoint 中断恢复测试；
- Tool 超时、权限拒绝、参数异常测试；
- 模型限流、超时、供应商失败测试；
- Run 重复提交和重复消息幂等测试；
- 并发上限与租约失效测试；
- 取消传播测试；
- Token/Step/Cost Budget 边界测试；
- Trace 父子 Span 关联测试；
- 安全测试：伪造身份、Prompt Injection、越权 Tool、敏感输出。

## 14. 验收标准

- 至少一个 Agent 可通过 Runtime 调用 Retriever 和 Mock Tool 完成端到端任务。
- 每次 Run 有持久化状态、事件、TraceId 和配置版本引用。
- Worker 重启后可按策略恢复或明确失败，不产生重复副作用。
- Tool 每次调用均执行 Policy Check。
- 运行超时、取消、重试、预算耗尽均可验证。
- LangGraph 对象不直接暴露为公共 API 或数据库业务契约。
- Agent Worker 与 Ingestion Worker 资源隔离策略生效。
- 运行记录不泄露用户敏感身份、API Key 或内部凭据。

## 15. ADR 待决事项

- LangGraph Checkpointer 的具体存储实现与平台 Agent Checkpoint 的边界；
- 同步执行转异步执行的阈值；
- 长任务 Worker 的进程/部署模型；
- Memory 摘要的模型与保留策略；
- Agent Run 事件保留期限；
- 预算计量是否纳入模型供应商成本明细。

这些事项需通过 POC 和 ADR 冻结，不应未经验证写成既定事实。
