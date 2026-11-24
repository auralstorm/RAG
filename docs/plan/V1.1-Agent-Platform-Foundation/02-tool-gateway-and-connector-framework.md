# 02｜Tool Gateway 与 Connector Framework 详细设计

> 公共字段、状态、事件、权限与迁移映射见 [统一契约与跨版本演进规则](../../architecture/统一契约与跨版本演进规则.md)；本文件描述本版能力及增量，具体实现须通过契约与升级验收。

**版本：** V1.1 — Agent Platform Foundation  
**状态：** 研发设计基线  
**核心原则：** Agent 不直接访问企业系统；所有工具调用统一经过 Tool Gateway 与 Policy Engine。

---

## 1. 目标与范围

V1.1 建立统一工具调用底座，使 Agent 能安全调用平台能力和 Mock 企业系统。此版本优先完成 Contract、执行边界、权限、超时、限流、审计和适配器机制。

### 实现范围
- Tool Definition / Tool Contract；
- Tool Registry 的最小服务端注册机制；
- Tool Gateway 统一执行入口；
- JSON Schema 输入输出校验；
- Policy Check 与可信身份上下文传递；
- Tool Call 记录、Trace、Audit；
- REST / SQL / MCP Connector Adapter 接口；
- Mock Connector 与 Mock Tools；
- 超时、重试、幂等、熔断/并发限制基础能力；
- Secret Reference，不在 Tool Definition 中明文保存凭据。

### 非目标
- 不接入真实 HR/CRM/ERP 生产系统；
- 不提供任意 SQL 执行或任意 URL 请求；
- 不允许 Agent 自己注册生产 Tool；
- 不做 Connector Marketplace；
- 不开放有不可逆副作用的生产写操作；
- 不把 MCP Server 视为可信授权来源。

## 2. 术语与领域对象

### Tool
Agent 可调用的原子能力。Tool 是平台的业务调用契约，不等同于某个 Python 函数。

### Connector
负责连接外部系统或协议的适配器。一个 Connector 可暴露多个 Tool。

### Tool Definition
包含稳定 Tool Key、描述、输入输出 Schema、风险等级、权限要求、超时和执行策略。

### Tool Call
某次执行实例，必须有唯一 ID、调用主体、Agent Run、Tool Version、参数摘要、策略决策和结果状态。

### Connector Instance
某个外部系统连接配置，凭据通过 Secret Reference 关联。

## 3. 逻辑架构

```text
LangGraph Tool Node
       |
       v
Tool Gateway API / Application Service
       |
       +-- Tool Registry / Version Resolver
       +-- Input Schema Validator
       +-- Policy Engine
       +-- Budget / Rate Limit
       +-- Idempotency Manager
       +-- Execution Dispatcher
                 |
       +---------+-----------+
       |         |           |
    Native     REST        MCP
    Adapter   Adapter     Adapter
       |         |           |
       +---------+-----------+
                 |
          Mock / External System

Cross-cutting: Secret Manager · Audit · Trace · Metrics
```

## 4. Tool Contract

建议统一结构：

```json
{
  "tool_key": "mock.employee.lookup",
  "version": "1.0.0",
  "display_name": "Lookup Employee",
  "description": "Look up an employee using an authorized identifier",
  "input_schema": {
    "type": "object",
    "properties": {
      "employee_id": {"type": "string", "minLength": 1}
    },
    "required": ["employee_id"],
    "additionalProperties": false
  },
  "output_schema": {
    "type": "object",
    "properties": {
      "employee": {"type": "object"}
    },
    "required": ["employee"]
  },
  "risk_level": "LOW",
  "effect": "READ_ONLY",
  "required_permissions": ["employee:read"],
  "timeout_seconds": 10,
  "retry_policy": "READ_ONLY_TRANSIENT",
  "idempotency_required": false
}
```

Contract 要求：
- Tool Key 稳定且全局唯一；
- Version 遵循语义化版本或平台明确版本规则；
- 输入 Schema 禁止未声明字段；
- 输出 Schema 统一；
- 描述面向模型，但描述文本不具有授权效力；
- `risk_level` 与 `effect` 是平台策略字段，不能由模型输入；
- Secret 只允许引用 Secret ID，不允许写入 Schema 或 Prompt；
- Tool 版本升级应兼容旧 Run，或阻止旧 Run 恢复。

## 5. Tool 风险分级

| 等级 | 类型 | V1.1 策略 |
|---|---|---|
| LOW | 只读、低敏感 Mock 数据 | 可在显式授权下调用 |
| MEDIUM | 读取敏感业务数据或高频查询 | 更严格资源范围、脱敏和审计 |
| HIGH | 创建/修改业务数据 | V1.1 默认禁用生产执行；仅测试 Mock |
| CRITICAL | 删除、付款、权限变更等高风险 | V1.1 不开放 |

Tool 风险等级必须由管理员/平台配置，不由 Agent 或用户参数指定。

## 6. Tool Gateway 执行流程

1. 接收 Tool Call Request，验证调用方为受信 Runtime Service。
2. 解析 `run_id`、`agent_key`、`subject_context` 和 `tool_key`。
3. 检查 Tool 是否启用，版本是否匹配。
4. 校验 Agent Definition 是否绑定该 Tool。
5. 校验输入 JSON Schema 和业务约束。
6. 调用 Policy Engine，检查用户主体、Agent、资源范围、动作和环境。
7. 执行限流、并发配额和预算检查。
8. 对需要幂等的调用创建/读取 Idempotency Record。
9. 解析 Secret Reference，构建 Connector 执行上下文。
10. 通过对应 Adapter 执行。
11. 校验输出 Schema，进行敏感字段过滤。
12. 写 Tool Call 状态、Trace 和 Audit。
13. 返回标准 Tool Result。

任何步骤失败都必须返回稳定错误码，不能将异常堆栈或 Secret 返回给模型。

## 7. 统一请求/响应

### ToolCallRequest

- `tool_call_id`
- `run_id`
- `agent_key`
- `tool_key`
- `tool_version`
- `arguments`
- `idempotency_key`
- `deadline_at`
- `trace_context`

身份上下文由可信服务间认证与服务端上下文注入，不接受客户端任意声明的 `user_id` 作为最终授权主体。

### ToolCallResult

- `tool_call_id`
- `status`：SUCCEEDED / FAILED / DENIED / TIMED_OUT / CANCELLED
- `result`
- `error_code`
- `retryable`
- `latency_ms`
- `redaction_applied`
- `audit_event_id`

## 8. Connector Adapter Contract

统一接口建议：

- `validate_config(config) -> ValidationResult`
- `health_check(connection_ref) -> HealthResult`
- `execute(tool_definition, arguments, execution_context) -> ConnectorResult`
- `close()`（若连接需要资源释放）

Connector Adapter 不能自行决定用户权限。授权必须在 Gateway/Policy 层完成；Adapter 只负责协议和系统交互。

### REST Adapter
- 仅允许管理员配置的 Base URL 和 Path；
- 禁止 Tool 参数覆盖 Host、Scheme 或任意 URL；
- 使用 Endpoint Allowlist、出站网络限制和 SSRF 防护；
- TLS 校验默认开启；
- 超时、响应体大小和重定向次数有上限；
- Header Secret 通过 Secret Reference 注入。

### SQL Adapter
- 仅允许配置的数据源和受控 Query Template；
- 禁止模型生成任意 SQL 并直接执行；
- 参数化查询；
- 数据库账号只授予必要只读权限；
- 限制查询超时、行数、扫描量；
- 对列级敏感信息进行 Masking；
- V1.1 只允许 Mock DB 或专用只读测试数据源。

### MCP Adapter
- MCP Server 是协议端点，不是授权边界；
- 平台需注册 Server、Tool Manifest、版本和可信来源；
- 每次调用仍经过 Tool Gateway Policy；
- 禁止任意用户提供 MCP URL；
- Server 连接凭据通过 Secret Reference；
- 对 Tool Schema 做本地校验；
- 记录 Server 身份、Tool 名称、版本、调用耗时和错误；
- 连接失败、超时、协议异常要转成平台统一错误。

## 9. Mock Connector 设计

至少提供：
- `mock.employee.lookup`：根据固定测试 ID 返回模拟员工信息；
- `mock.directory.search`：模拟目录搜索；
- `mock.ticket.get`：模拟只读工单查询；
- `mock.calendar.availability`：模拟日历空闲查询。

Mock 数据必须明确标注，不得伪装成真实业务数据。测试数据不包含真实个人信息。

## 10. 安全与策略

- 每次调用都校验用户授权范围和 Agent 绑定范围。
- 防止 Confused Deputy：Agent 不能利用平台服务账号扩大调用者权限。
- 采用最小权限 Service Identity。
- Tool 参数进行 Schema + 业务校验。
- 输出进行字段级脱敏。
- 日志不得记录 Secret、Authorization Header、完整敏感参数。
- Prompt Injection 不得改变 Tool Allowlist、Policy 或 Connector Endpoint。
- 工具执行失败不能自动切换到更高权限凭据。
- 生产写操作默认关闭，后续版本需审批、幂等和补偿。

## 11. 幂等、重试与副作用

- 只读 Tool 可在瞬时网络错误下有限重试。
- 有副作用 Tool 必须要求 Idempotency Key。
- Idempotency Record 以主体、Tool、业务操作和 Key 组成唯一约束。
- 重复请求返回既有执行结果或状态，不重复执行。
- 超时不等于外部操作失败；对不确定结果应进入 UNKNOWN/RECONCILIATION，而不是盲目重试。
- V1.1 不开放生产副作用 Tool，但 Contract 必须预留该语义。

## 12. 并发与稳定性

- Tool 级并发上限；
- Connector Instance 级连接池/并发上限；
- 用户/Agent/系统级限流接口；
- 请求 deadline 贯穿 Gateway 与 Adapter；
- 熔断器只作为保护机制，状态变化需可观测；
- 对慢 Connector 使用隔离执行池；
- 限制响应体大小和最大结果条数；
- 超时后尽可能取消底层请求。

## 13. API 建议

- `GET /api/v1/tools`：查询当前主体可见的 Tool Catalog。
- `GET /api/v1/tools/{tool_key}`：查看 Tool Schema 和说明。
- `GET /api/v1/connectors`：管理员查询 Connector。
- `POST /api/v1/connectors/{id}/health-check`：管理员触发健康检查。
- `GET /api/v1/tool-calls/{tool_call_id}`：查询调用状态（受权限限制）。

实际执行接口建议仅允许 Runtime Service 内部调用，不对普通浏览器直接开放。

## 14. 数据与审计

每次调用至少记录：
- Tool Call ID、Run ID、Agent Key、Tool Key/Version；
- 发起主体的匿名/内部引用；
- Policy Decision ID 和拒绝原因；
- 参数摘要（脱敏）；
- 开始/结束时间、耗时；
- 结果状态、错误码；
- Connector Instance 引用；
- Trace ID；
- 幂等键的哈希或引用，不记录敏感原文。

## 15. 测试与验收

- Tool Schema 正反向校验；
- Agent 未绑定 Tool 时拒绝；
- 用户无权限时拒绝；
- 参数注入、额外字段和类型错误拒绝；
- REST SSRF/重定向/超时边界测试；
- SQL 参数化和只读约束测试；
- MCP Server 未注册/版本不符/协议错误测试；
- Secret 不出现在日志、Trace、响应和模型上下文；
- 重复幂等请求不重复执行；
- 并发超限和熔断行为可验证；
- 输出字段脱敏测试；
- Tool Trace 与 Agent Run Trace 关联。

**Exit Criteria：** 至少一个 Agent 可经 Gateway 调用 Mock Tool；所有调用经过 Policy、Schema、限流和 Trace；越权与恶意参数测试通过；未授权的生产写操作无法执行。
