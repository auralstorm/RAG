# 05｜V1.1 代码结构与研发任务拆分

> 公共字段、状态、事件、权限与迁移映射见 [统一契约与跨版本演进规则](../../architecture/统一契约与跨版本演进规则.md)；本文件描述本版能力及增量，具体实现须通过契约与升级验收。

**版本：** V1.1 — Agent Platform Foundation  
**状态：** 研发执行基线草案  
**架构策略：** 模块化单体 + 独立 Agent Worker/队列；暂不全面微服务化。

---

## 1. 研发目标

在 V1.0 既有代码库上增量交付 Agent Runtime、Tool Gateway、Connector Adapter、Memory/Context、Policy 扩展和 Agent Trace。

不得重建 V1.0 已完成的 RAG、Model Gateway、Identity、RBAC、Audit、Chat/Admin 基础设施。

## 2. 推荐目录结构

```text
repo/
├── apps/
│   ├── api/
│   └── agent-worker/
├── backend/
│   └── app/
│       ├── modules/
│       │   ├── agent/
│       │   │   ├── domain/
│       │   │   ├── application/
│       │   │   ├── infrastructure/
│       │   │   └── api/
│       │   ├── runtime/
│       │   │   ├── graph/
│       │   │   ├── adapters/
│       │   │   ├── checkpoint/
│       │   │   └── events/
│       │   ├── tool_gateway/
│       │   ├── connector/
│       │   │   ├── contracts/
│       │   │   ├── adapters/
│       │   │   │   ├── rest/
│       │   │   │   ├── sql/
│       │   │   │   └── mcp/
│       │   │   └── mock/
│       │   ├── memory/
│       │   ├── context/
│       │   ├── policy/
│       │   ├── observability/
│       │   └── budget/
│       ├── shared/
│       └── workers/
├── packages/
│   ├── contracts/
│   └── sdk/
├── frontend/
│   ├── apps/
│   │   ├── chat/
│   │   └── admin/
│   └── packages/
│       ├── ui/
│       ├── api-client/
│       └── shared/
├── infra/
├── migrations/
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── contract/
│   ├── security/
│   └── load/
└── docs/
```

实际目录与 V1.0 源码仓合并。前端沿用 [ADR-0014](../../adr/0014-monorepo-and-independent-frontend-apps.md) 的两个独立应用和 pnpm 公共包；API/Worker 示例表示进程入口，不增加新的前端应用。领域依赖方向保持清晰。

## 3. 模块依赖规则

- API 层只负责协议适配、认证上下文和输入输出转换。
- Application 层编排用例，不直接依赖 LangGraph/MCP SDK 具体实现。
- Domain 层定义 Agent Run、Tool Call、Policy、Budget 等业务规则。
- Infrastructure 层实现 PostgreSQL、Redis、RabbitMQ、LangGraph、MCP 等适配。
- Runtime 只能通过 Tool Gateway、Retriever API、Model Gateway 访问能力。
- Connector Adapter 不得直接决定用户授权。
- Memory 模块不得绕过数据生命周期服务删除/保留内容。
- Observability 不得将敏感业务数据无差别复制到 Trace。

## 4. Epic 与任务清单

任务优先级：
- P0：本版本上线必需；
- P1：增强项，若不影响核心 Exit Criteria 可延后；
- P2：明确留给后续版本。

### E1 — Runtime Foundation

**E1-01 Agent Run Domain Model（P0）**
- 定义 Run 状态机、状态迁移和领域错误；
- 定义 Agent Definition 最小配置模型；
- 实现创建、启动、完成、失败、取消、暂停等领域服务。
- 验收：非法状态迁移被拒绝；终态不可直接恢复；状态变更有测试覆盖。

**E1-02 LangGraph Adapter（P0）**
- 实现 Graph Factory；
- 将平台 Agent Definition 转换为受控 Graph；
- 节点通过 Model Gateway、Retriever API、Tool Gateway 适配器访问能力。
- 验收：替换 LangGraph 版本/实现不要求修改 Agent 业务 API；不泄露框架对象。

**E1-03 Agent Worker（P0）**
- 新增专用队列和 Worker；
- 支持 Run 租约、心跳、超时和重复消息幂等；
- 与 Ingestion Worker 资源隔离。
- 验收：Worker 重启后 Run 可恢复或进入明确失败状态；重复消息不重复执行。

**E1-04 Run Event Stream（P0）**
- 持久化关键事件；
- SSE 推送状态和进度；
- 支持断线后按序号补拉。
- 验收：事件不乱序；断线重连后客户端状态可恢复。

### E2 — Checkpoint & Recovery

**E2-01 Checkpoint Adapter（P0）**
- 定义平台 Checkpoint Contract；
- 实现存储、读取、版本和过期策略；
- 不保存 Secret。
- 验收：保存后可恢复；Schema 不兼容时安全失败。

**E2-02 Recovery Scheduler（P0）**
- 扫描租约过期和中断 Run；
- 判断是否允许恢复；
- 恢复前校验配置版本、身份和 Policy。
- 验收：过期 Run 不会被多个 Worker 同时恢复；不兼容 Run 不自动继续。

**E2-03 Cancellation（P0）**
- 实现取消请求、Worker 取消信号和终态落库；
- 对下游模型/工具请求尽可能传播取消。
- 验收：取消后不再启动新 Tool Call；已发生副作用需记录结果状态。

### E3 — Tool Gateway

**E3-01 Tool Contract（P0）**
- 定义 Tool Definition、Input/Output Schema、风险和 Effect；
- 建立版本化与校验器。
- 验收：无效 Schema、未知字段和版本冲突被拒绝。

**E3-02 Tool Registry（P0）**
- 注册 Mock Tool、查询可用工具；
- 绑定 Agent Allowlist。
- 验收：未注册或未绑定 Tool 无法执行。

**E3-03 Tool Execution Pipeline（P0）**
- 实现参数校验、Policy Check、Budget、Rate Limit、Dispatch、Output Validation；
- 写 Tool Call 状态。
- 验收：每次调用可追踪；Policy Deny 不触达 Connector。

**E3-04 Idempotency（P0）**
- 建立幂等记录与唯一约束；
- 处理重复请求和执行结果未知状态。
- 验收：相同 Key 不重复执行；不同主体不能错误共享幂等结果。

**E3-05 Output Redaction（P0）**
- 支持字段脱敏和结果大小限制；
- 不将凭据或内部 Token 返回模型。
- 验收：敏感字段在模型输入、日志和 Trace 中均按策略处理。

### E4 — Connector Framework

**E4-01 Connector Adapter Interface（P0）**
- 定义配置校验、健康检查、执行和关闭接口；
- 统一 Connector Result。
- 验收：Mock Adapter 可替换实现，不改变 Tool Gateway Contract。

**E4-02 Mock Connector（P0）**
- 提供员工查询、目录搜索、工单读取等模拟工具；
- 固定测试数据和错误场景。
- 验收：测试数据明确标记 Mock；不包含真实个人数据。

**E4-03 REST Adapter Skeleton（P1）**
- 管理员配置 Endpoint Allowlist；
- 固定 Base URL、Path Template 和参数映射；
- 超时、响应大小和 TLS 校验。
- 验收：用户参数无法改变目标 Host；SSRF 测试通过。

**E4-04 SQL Adapter Skeleton（P1）**
- 仅支持预定义参数化查询模板；
- 只读账号、超时和行数限制。
- 验收：不能执行任意 SQL；注入测试通过。

**E4-05 MCP Adapter Skeleton（P1）**
- 注册受信 Server；
- 读取 Manifest 并校验 Tool Schema；
- 调用仍走 Gateway Policy。
- 验收：未注册 Server 无法连接；MCP Tool 无法绕过 Policy。

### E5 — Memory & Context

**E5-01 Token Budget Manager（P0）**
- 读取 Model Gateway 模型能力；
- 分配输入/输出预算；
- 超限按既定优先级裁剪。
- 验收：上下文不超过预算；系统指令和关键证据不被静默截断。

**E5-02 Conversation Summary（P0）**
- 定义摘要 Schema；
- 实现异步摘要和版本替换；
- 保留原始消息引用。
- 验收：摘要失败不影响会话；事实/推断/待确认项可区分。

**E5-03 Task Memory（P0）**
- 保存当前 Run 的关键事实、步骤和结果引用；
- 与 Checkpoint 分离。
- 验收：可恢复任务状态；不同 Run/用户数据隔离。

**E5-04 Memory Lifecycle（P0）**
- 设计 TTL、删除和关联清理；
- 对接现有用户会话删除策略。
- 验收：删除任务覆盖 Summary、Task Memory、Checkpoint 和缓存。

### E6 — Policy, Trace & Governance

**E6-01 Agent Run Policy（P0）**
- 定义 agent.run、agent.resume、agent.cancel；
- 绑定主体和 Agent 资源范围。
- 验收：无权用户不能运行或读取他人 Run。

**E6-02 Tool Invoke Policy（P0）**
- 定义 tool.invoke、connector.use；
- 每次执行时重新授权。
- 验收：Prompt 不能提升权限；策略拒绝在 Connector 调用前生效。

**E6-03 Agent Trace（P0）**
- Run/Step/Model/Tool/Retriever Span 关联；
- 记录耗时、Token、错误和配置版本。
- 验收：Trace 能重建调用链，不泄露敏感参数。

**E6-04 Audit Integration（P0）**
- 记录 Tool 管理、Connector 配置、策略变更和高风险动作；
- 敏感字段脱敏。
- 验收：审计记录可查询且无普通删除入口。

### E7 — Chat / Admin 最小体验

**E7-01 Chat Agent Entry（P0）**
- 在 Chat 中选择/进入 V1.1 固定 Agent；
- 展示 Run 状态、进度、错误和 TraceId；
- 保留 V1.0 Standard RAG 入口。
- 验收：普通知识问题仍可走 Standard RAG；Agent Run 状态准确。

**E7-02 Admin Runtime Monitor（P1）**
- 展示运行总量、成功/失败、耗时、队列积压；
- 不提供 V1.2 Agent Builder 功能。
- 验收：聚合指标与运行数据一致，身份信息遵守现有脱敏规则。

## 5. 任务依赖

```text
E1-01 Domain Model
   ├── E1-02 LangGraph Adapter
   ├── E3 Tool Contract -> E3 Execution Pipeline
   │                         |
   │                         v
   │                    E4 Mock Connector
   ├── E2 Checkpoint / Recovery
   ├── E5 Context / Memory
   └── E6 Policy / Trace
              |
              v
        E7 Chat Integration
              |
              v
        Integration / Security / Load Tests
```

## 6. Definition of Done

每个任务完成必须满足：
- 代码合并并通过 Review；
- 单元测试和必要集成测试通过；
- API/Schema/配置文档更新；
- 权限与错误路径测试完成；
- Trace/Audit 已接入（适用时）；
- 无明文 Secret；
- 有部署/迁移说明；
- 任务验收证据可复核。

## 7. V1.1 代码质量门禁

- Python 类型检查、Lint、Format；
- Frontend TypeScript 检查；
- Domain 单元测试；
- Contract 测试；
- Integration Test；
- Security Test；
- Worker 幂等与恢复测试；
- 基础 Load Test；
- 依赖漏洞扫描和 Secret Scan。

## 8. 明确禁止事项

- Agent Runtime 直接访问 Elasticsearch；
- Agent 直接调用 MCP/REST/SQL；
- Tool Adapter 自行判断用户权限；
- 把 LangGraph State 当平台 API；
- 把 Redis 当 Agent Run 唯一事实来源；
- 对任意 SQL/URL/代码执行开放模型自由输入；
- 在 V1.1 抢做 Agent Builder、Multi-Agent 或完整 Workflow；
- 为了演示而关闭 Policy、Audit、Budget 或超时控制。

## 9. 本轮补充任务

| ID | 任务 | 优先级 | 验收 |
|---|---|---|---|
| E1-05 | Definition/Run 向 V1.2 的身份、Tool Key 和配置版本映射 | P0 | 保留来源配置与 Hash，旧入口复用 Registry Adapter，无越权扩大 |
| E2-04 | ApprovalRequest/Decision 与旧回调 Contract | P0 | Mock 覆盖批准/拒绝/过期/重放；审批参数变化失效 |
| E6-05 | 企业内资源授权验证 | P0 | 用户/组织/KB 及工具范围服务端校验，负向越权失败 |

这些任务闭合既有版本兼容和安全协议，不将完整 V1.4 审批中心纳入 V1.1。
