# V1.3-05 Multi-Agent Evaluation、Observability 与质量治理

> 公共字段、状态、事件、权限与迁移映射见 [统一契约与跨版本演进规则](../../architecture/统一契约与跨版本演进规则.md)；本文件描述本版能力及增量，具体实现须通过契约与升级验收。

## 1. 目标

将 V1.2 Agent Evaluation 扩展到规划质量、任务执行、工具使用、Agent 协作、证据质量、安全性、恢复能力、成本和延迟。不能只用最终答案相似度评估复杂 Agent。

## 2. Evaluation 分层

| 层级 | 评测对象 | 关键指标 |
|---|---|---|
| Planner | 任务拆解与 DAG | Goal Coverage、Invalid Plan Rate、Dependency Accuracy |
| Executor | 执行过程 | Task Success、Retry Rate、Recovery Rate |
| Tool | 工具调用 | Tool Selection、Argument Validity、Policy Compliance |
| Agentic RAG | 证据检索 | Recall、Evidence Coverage、Citation Correctness |
| Multi-Agent | 协作质量 | Handoff Success、Worker Agreement、Conflict Detection |
| Safety | 安全边界 | Unauthorized Action Rate、Injection Resistance |
| System | 运行效率 | P50/P95 Latency、Token、Cost、Concurrency |

## 3. Golden Dataset

每条 Case 建议包含：
- 用户任务与身份/权限上下文
- 预期路由模式（Standard RAG / Agentic RAG / Multi-Agent）
- 参考任务拆解或关键约束
- 必须引用的证据或允许证据范围
- 预期结果结构和关键事实
- 不允许执行的动作
- 预期人工审批点
- 预算、时延和最大步骤约束
- 难度、风险、标签和版本

数据集覆盖：
- 简单问题不应误触发 Multi-Agent。
- 多跳问题需要多轮检索。
- 不完整问题需要澄清。
- 冲突证据需要显式呈现。
- Worker 输出错误或互相矛盾。
- 工具限流、超时、权限拒绝。
- Prompt Injection 和越权请求。
- Checkpoint 恢复、取消和预算耗尽。

## 4. 关键指标定义

- Task Success Rate：满足预设任务完成标准的 Run 比例。
- Plan Validity Rate：Schema 与 DAG 约束合法的 Plan 比例。
- Plan Efficiency：实际 Step 数与参考/合理 Step 数的比值。
- Evidence Coverage：关键 Claim 中有有效支持证据的比例。
- Citation Correctness：引用真实存在且支持 Claim 的比例。
- Tool Policy Compliance：所有 Tool 调用均通过策略校验的比例。
- Recovery Success Rate：可恢复故障中成功恢复的比例。
- Handoff Success Rate：成功完成并通过验证的委派任务比例。
- Budget Violation Rate：超出预算仍发起调用的比例，目标必须为 0。
- Unauthorized Action Rate：未经授权动作成功执行的比例，目标必须为 0。

## 5. Trace 数据模型

Trace 采用层级 Span：
- Run Span
- Planning Span
- Plan Revision Span
- Task Span
- Step Span
- Model Call Span
- Retriever Span
- Tool Span
- Handoff / Child Run Span
- Human Interaction Span
- Verification Span

Span 属性：
`principal_ref`（匿名化引用）、`agent_id`、`agent_version_id`、`run_id`、`plan_id`、`task_id`、`step_id`、`tool_id`、`model_id`、`policy_decision_ref`、`status`、`latency_ms`、`token_usage`、`cost_estimate`。

遵循平台既定 Trace 隐私规则：默认匿名；身份溯源需高权限、理由、二次确认和审计。不要把原始密钥、完整访问令牌或不必要的用户敏感信息写入 Span。

## 6. Runtime Events 与 UI

事件流用于 Chat 实时展示和 Admin 调试：
- run.started
- plan.created
- task.started / task.completed / task.failed
- step.started / step.completed / step.failed
- agent.handoff.started / completed
- evidence.collected
- approval.required / decided
- run.waiting_approval / run.waiting_input
- run.replanned
- run.completed / failed / cancelled

事件需带 `event_id`、`run_id`、单调序号、时间、类型、payload schema version。客户端断线后可按游标补拉，不依赖 SSE 连接本身保存状态。

## 7. 可观测性界面

Chat 用户视图：
- 当前阶段与简洁进度
- 正在执行/等待用户输入/等待审批/已完成/失败
- 可解释的任务摘要，不暴露内部思维链
- 最终结果、引用、产物和 Trace ID

Admin / Playground 视图：
- Plan DAG 与 revision
- Task / Step 状态、耗时、重试
- Model / Tool 调用摘要
- Evidence 列表和 Claim 映射
- Worker 委派关系
- Policy Decision、Approval 和 Guardrail 事件
- Token、成本、预算消耗
- 错误分类和恢复历史

不得把模型隐藏思维链作为产品功能展示；展示结构化计划、执行事件、工具调用摘要和证据即可。

## 8. 发布门禁

Agent Version 发布前：
- Schema / 静态校验通过。
- Golden Dataset 基线评测通过。
- 安全测试集无关键失败。
- Unauthorized Action Rate = 0。
- Budget Violation Rate = 0。
- 关键任务成功率达到项目设定阈值。
- P95 延迟和成本满足预算。
- 评测报告绑定 Agent Version、Prompt、Model、Tool 和 Dataset Version。

阈值需在项目启动时由产品、架构和业务共同确定，不能用未经业务验证的通用数字冒充行业标准。

## 9. 回归与线上评测

- 每次 Prompt、Model、Tool Schema、Retriever Profile 变化触发回归。
- 发布后按采样策略评估真实运行质量。
- 线上反馈不能直接自动改写 Prompt 或 Agent Definition。
- 发现质量回退时支持版本回滚。
- 数据集和评测结果不可覆盖历史版本。

## 10. 验收标准

- 可对 Planner、Executor、RAG、Worker 和安全分别评测。
- Trace 能重建 Run 的执行结构。
- 事件支持断线续读。
- UI 不暴露 Chain-of-Thought。
- 发布门禁可阻止关键安全回归。
- 线上问题可关联到确切 Agent Version 和配置快照。

## 11. 公共字段与版本复用

复用 V1.2 Dataset/Profile/Runner/Result/Report/Gate，仅增量增加指标和 Span。持久化用量使用 token_usage_json、结束时间 finished_at；Span token_usage、principal_ref 是观测映射，不能覆盖授权主体或公共状态。

UI 的“等待人工”聚合 WAITING_APPROVAL/WAITING_INPUT，执行计划阶段来自 execution_phase；“等待人工”仅作 UI 聚合显示，公共事件保持 run.waiting_approval/run.waiting_input，详情见统一契约第 4 节。
