# 02｜生产 Connector 与集成治理

> 版本：V1.4。复用 [V1.1 Tool/Connector Contract](../V1.1-Agent-Platform-Foundation/02-tool-gateway-and-connector-framework.md)，本版执行域和增量见 [统一契约](../../architecture/统一契约与跨版本演进规则.md) 与 [06](06-database-api-and-contract-design.md)。

## 1. 本版建设深度

V1.1 的受控 Adapter、Tool Registry、Policy 和 Mock 是基础。V1.4 让已验收的 Connector Instance 进入真实系统，增加凭据生命周期、网络边界、业务效果确认、生产准入和停用流程；工单系统为首个试点，其他系统按业务优先级扩展。

每个 Adapter 继续实现配置校验、健康检查、执行和资源释放，Gateway 负责身份/Tool Binding/Policy/预算/审计。Workflow 不直接持有外部凭据，也不绕过 Gateway 自建 HTTP/SQL/MCP 客户端。

## 2. 连接对象与配置版本

复用 connectors、connector_instances、tools、tool_versions。Connector Definition 表达协议能力；Instance 表达环境、Endpoint/Secret 引用及当前配置版本；Tool Version 固定操作 Schema、风险、效果、重试/幂等能力和 Binding。

新增配置能力通过 connector_config_versions 或既有不可变配置表存储，实际复用位置在 M0 盘点。Workflow Version 固定 Tool/Connector 配置版本；Secret 只固定引用，轮换在受控凭据服务中解析，并在审计记录实际使用的 Secret 版本标识。

| 生产配置维度 | 需要冻结的内容 |
|---|---|
| 身份和认证 | 服务身份、调用方最小 Scope、OAuth/API Key/mTLS 等真实系统所需方式 |
| 网络 | Base URL、Path/Method Allowlist、TLS 校验、代理、重定向/SSRF 与出站限制 |
| 数据 | 输入/输出 Schema、字段映射、敏感分级、大小/行数/保留规则 |
| 稳定性 | 连接/读取 Deadline、限流、并发、重试预算、熔断及健康检测 |
| 副作用 | 幂等模式、业务唯一键、查询/确认方法、未知提交和补偿方式 |
| 运营 | Owner、环境、配置版本、凭据轮换、生产准入/停用及回滚 Runbook |

健康状态沿用既有枚举；“健康”只说明连接可用，生产准入另存审批/验证记录，不能通过一次 health-check 自动开放写入。

## 3. 协议适配要求

### REST

Endpoint 由管理员配置，参数不能覆盖 Host/Scheme/任意 URL。校验 TLS、重定向目标、请求体和响应体上限；超时区分未发送、已发送待结果、结果确认失败。记录外部 request/operation reference 和字段脱敏后的响应摘要。

按目标 API 明确 429/5xx/业务拒绝/冲突等错误的含义。HTTP 200 不等于业务成功；HTTP 超时也不证明业务失败。创建工单的字段和认证方式必须依据实际接口资料及 Sandbox 调用冻结。

### SQL

优先受控只读 Query Template、参数化和表/列 Allowlist。生产写 SQL 不默认开放；确需使用时限定已审核事务模板、独立账号、业务唯一约束和回查方法，纳入同一审批/业务动作协议。模型生成 SQL 不能直接作为执行指令。

### MCP

固定受信 Server 和工具清单/版本，校验 Schema 及调用身份；每次仍经 Gateway Policy。Server 宣称的 idempotent、风险或权限能力需要平台验收，不能因协议兼容就默认具备生产授权。

## 4. 工单能力验收清单

| 能力 | P0 验证 | 无此能力时的行为 |
|---|---|---|
| 创建工单 | 参数、权限、业务成功判定和外部 ID | 禁止生产流程启用 |
| 外部防重复 | 原生幂等 Key，或已验证的业务唯一键约束 | 自动写入保持关闭；不能仅靠本地去重宣称外部恰好一次 |
| 按操作 Key 回查 | 定位“请求已提交但响应丢失”的事实 | UNKNOWN 转人工对账，生产上线需确认允许的处理方式 |
| 获取工单 | ID/状态/内容的权限受控查询 | 结果确认 Gate 不通过 |
| 取消/撤回工单 | 当前状态、权限及可逆性 | 删除示例补偿 Binding，采用业务认可的人工补救 |
| 凭据轮换/失效 | 旧实例恢复与新请求重新授权 | 写入暂停并告警，不尝试扩大权限 |

`ticket.create` 等 Tool Key 为设计建议，正式名称、版本与 Schema 在 M0 统一注册。平台内 draft_id、Business Action ID 和外部 ticket_id 分开保存，不能用“申请已受理”冒充“外部工单已创建”。

## 5. 业务动作与调用 Attempt

Business Action 是一次逻辑外部效果；Tool Call/Attempt 是一次实际调用。一个 Action 可有受控重试/确认调用，所有写入 Attempt 使用相同逻辑操作 Key、参数 Hash 与 Binding，不能用新 Key 重试未知提交。

调用前：持久化 Action、冻结参数/Binding、当前 Policy、审批及授权关联 → Gateway 检查 → 事务外网络调用 → 记录外部响应/确认结果 → 条件更新 Action 和事件。外部效果与数据库事务不构成原子事务，恢复依赖持久操作事实和对账。

Gateway 的 V1.4 结果增加 commit_state：NOT_STARTED / CONFIRMED_SUCCEEDED / CONFIRMED_FAILED / UNKNOWN。内部 Workflow Action 消费此字段；旧 Runtime 响应仍使用兼容 ToolCallResult，UNKNOWN 映射为已支持的失败/超时状态、retryable=false 和明确错误语义，不诱导旧调用方自动重放。Tool Call 持久化保留既有字段并增量保存执行域及 commit_state。

| 提交事实 | 允许动作 |
|---|---|
| 确认未发出 | 当前授权有效时用原 Key 受控重试 |
| 外部确认成功 | 保存外部 ID，进入 confirm；禁止再次创建 |
| 外部确认失败且无副作用 | 按已冻结错误规则重试或失败 |
| 未知/响应无法解析 | 原 Key 回查；仍未知则 NEEDS_REVIEW，停止新写入 |

租约/fencing_token 防止平台状态被旧 Worker 推进；外部系统仍需幂等/唯一键约束。两个机制分工，不能把租约锁当成外部写入不会重复的证明。

## 6. 凭据、停用与发布

管理员创建实例时只写 Secret Reference；普通用户、Workflow JSON、Agent Prompt、Trace 不接触明文凭据。配置/凭据变更写独立审计，关联服务身份和实际版本。

生产推广：Mock Contract → Sandbox/只读测试 → 幂等与对账 POC → 权限/网络/隐私评审 → 写入准入记录 → 限制流程/用户试点 → 观察并由业务负责人验收。阶段不得仅凭配置状态前进。

停用阻止新动作派发；在途写入保留事实并进入确认/对账，不能抹掉已发出的操作。回滚配置保持旧 Workflow 快照可解释；旧凭据无效时暂停执行并由授权管理员处理。

## 7. 测试与证据

正反例 Schema、认证失效、权限拒绝、SSRF、响应超限、429/超时、业务失败、幂等冲突、响应丢失、轮换中恢复及停用中的在途操作必须有测试。证据记录接口版本、环境、配置 Hash、Key、外部引用和脱敏结果；生产写入准入须有真实系统 Sandbox/试点记录，不能复用 Mock 结果替代。
