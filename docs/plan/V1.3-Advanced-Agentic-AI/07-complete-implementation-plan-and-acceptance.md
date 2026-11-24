# V1.3-07 完整研发实施计划与阶段验收标准

> 公共字段、状态、事件、权限与迁移映射见 [统一契约与跨版本演进规则](../../architecture/统一契约与跨版本演进规则.md)；本文件描述本版能力及增量，具体实现须通过契约与升级验收。

## 1. 研发目标

以可控复杂执行为交付目标，不以“做出 Multi-Agent Demo”为完成标准。最终必须具备可配置、可观测、可恢复、可评测和受策略约束的 Agentic Runtime。

## 2. 开发前置条件

进入 V1.3 前确认：
- V1.1 Runtime、Tool Gateway、Checkpoint 基础能力可用。
- V1.2 Agent Registry、不可变发布快照、Playground、Evaluation 可用。
- Model Gateway、Retriever API、Policy Engine 有稳定 Contract。
- Agent Version 能绑定 Prompt、Model、Tools、Knowledge Bases 和权限范围。
- Trace / Audit 的匿名化和身份生命周期规则已落实。

若前置能力缺失，先补齐，不要在 V1.3 重造一套平行机制。

## 3. 里程碑

### M0：架构冻结与 Contract
交付：
- Runtime State Model
- Plan / Task / Step Schema
- Run 状态机
- Planner / Executor / Checkpoint Contract
- Delegation Contract
- Evidence Contract
- Human Interaction Contract
- API OpenAPI 初版
- 真实协作场景、单 Agent 基线和质量/成本/延迟收益标准
- Run/Step/Checkpoint 增量迁移、旧创建/SSE/审批回调兼容方案

验收：领域模型不依赖 LangGraph 内部类型；所有外部能力均经过平台 Gateway。

### M1：Planner 与 DAG Executor
交付：
- Intent / Complexity Router
- Planner Prompt 与结构化输出
- Plan Validator
- DAG Scheduler
- Task / Step 状态持久化
- 有界 Retry / Timeout / Budget

验收：复杂任务可生成 DAG；非法计划不会执行；并行任务遵循依赖；预算超限停止新调用。

### M2：Agentic RAG
交付：
- Query Decomposition
- Multi-round Retrieval
- Evidence Store / Dedup
- Parent Context Expansion
- Claim-level Verification
- Citation Validation

验收：多跳问题能迭代检索；简单问题仍走 Standard RAG；ACL 每轮生效；引用可定位原文。

### M3：Supervisor / Worker Multi-Agent

进入条件：使用 M0 的真实场景与单 Agent 基线核验协作价值。收益未证实则提交范围 ADR，由产品/架构决定是否延后，并同步路线图、README、测试和 DoD；确认前不把此里程碑擅自删除，也不按版本号直接启动实现。

准入后交付：
- Worker Agent allowlist
- Delegation Contract
- Parent / Child Run
- 并行调度与资源配额
- 结果聚合和冲突检测
- Worker 失败隔离

验收：至少两个独立 Worker 可并行完成子任务；权限不继承扩大；父子 Run 可追踪；深度与预算限制有效。

### M4：Human-in-the-loop 与恢复
交付：
- Clarification / Approval / Review
- Approval Token
- Pause / Resume / Cancel
- Checkpoint 恢复
- 故障分类与恢复策略
- 高风险 Tool 门禁

验收：未审批高风险 Tool 无法执行；参数变化使审批失效；恢复不重复已完成的幂等步骤；权限变化后恢复重新校验。

### M5：Evaluation、Observability 与发布门禁
交付：
- Agentic Golden Dataset（复用 V1.2 的 Dataset/Runner/Report/Gate，新增指标）
- Planner / Execution / RAG / Multi-Agent / Safety Metrics
- Trace DAG 和事件流
- Playground 可视化
- Release Gate 与回归报告

验收：评测结果绑定确切版本；关键安全指标达标；Trace 可重建执行路径；发布失败可阻止上线。

### M6：灰度、文档与交付
交付：
- 内部灰度
- 压测和故障演练
- 安全测试报告
- 运行手册和故障手册
- API / Schema 文档
- V1.3 发布包

验收：核心场景通过端到端测试；有回滚方案；运维能定位失败 Run。

## 4. 建议研发顺序

1. 先冻结 Schema / Contract，避免前后端和 Runtime 各自定义状态。
2. 先完成单 Agent Planner + DAG Executor。
3. 再完成 Agentic RAG，复用现有 Retriever API。
4. 再做 Worker Delegation，控制 Multi-Agent 复杂度。
5. 再做 Human-in-the-loop 和 Checkpoint 恢复。
6. 最后做评测门禁、可观测 UI 和灰度。

不建议第一周就并行开发 Planner、Multi-Agent UI、Workflow Designer 和真实业务 Connector。

## 5. 角色分工建议

| 角色 | 主要职责 |
|---|---|
| 架构/Tech Lead | Contract、状态机、风险边界、ADR |
| Backend Runtime | Planner、Executor、Checkpoint、Delegation |
| RAG Engineer | Query Decomposition、Evidence、Verification |
| Frontend | Run Timeline、Plan DAG、Approval、Trace UI |
| Platform / DevOps | Queue、配额、监控、压测、故障演练 |
| QA / Evaluation | Golden Dataset、自动化、安全和回归评测 |
| Security Reviewer | Policy、Prompt Injection、审批绕过和数据隔离 |

## 6. 测试策略

### Unit
- Plan Schema / DAG 无环
- Budget Counter
- Retry Classifier
- State Transition
- Approval Parameter Hash
- Evidence Dedup / Claim Mapping

### Integration
- Model Gateway
- Retriever API
- Tool Gateway
- PostgreSQL / Redis / RabbitMQ
- Object Storage
- Checkpoint Restore

### End-to-end
- 多文档对比
- 多跳检索
- 双 Worker 并行
- Worker 冲突
- Tool Timeout
- Policy Deny
- Approval / Reject / Expire
- Cancel / Resume
- Budget Exhaustion

### Security
- Prompt Injection
- Tool 参数污染
- Worker 权限提升
- Run ID 越权访问
- Approval 重放
- Checkpoint 篡改
- 敏感数据进入 Trace

## 7. 发布阻断项

以下任一项未通过，不得发布：
- 未授权 Tool 调用成功。
- 高风险 Tool 可绕过审批。
- Run/Task/Step 状态无法恢复或出现不可解释的不一致。
- Checkpoint 保存明文 Secret。
- ACL 绕过或跨用户数据泄露。
- 预算上限不能阻止新调用。
- 关键证据引用错误或伪造。
- Worker 可无限递归或无限并发。
- Trace 暴露不应访问的身份信息。

## 8. V1.3 交付验收清单

- [ ] 单 Agent 复杂任务规划与 DAG 执行
- [ ] Query Decomposition / Multi-hop Retrieval
- [ ] Evidence Collection / Claim Verification
- [ ] Supervisor-Worker 两层协作
- [ ] Worker 最小权限委派
- [ ] Retry / Timeout / Budget / Cancel
- [ ] Checkpoint / Resume
- [ ] Human Clarification / Approval / Review
- [ ] Tool Policy 与审批门禁
- [ ] Run Timeline / Plan DAG / Trace
- [ ] Agentic Evaluation 与发布门禁
- [ ] 安全测试、压测和故障演练
- [ ] V1.2 Agent 向后兼容
- [ ] V1.4 Workflow 边界未被侵入
- [ ] Multi-Agent 业务收益准入已通过，或有已批准范围 ADR 及同步后的验收清单
- [ ] Run/Step/Checkpoint 存量迁移、旧 API/审批回调与未知状态兼容通过

## 9. 版本完成定义（DoD）

V1.3 不是“Planner 能输出 JSON”或“多个 Agent 能互相调用”就算完成。必须同时满足：
- 可控：有 Schema、权限、预算、深度和并发边界。
- 可恢复：Checkpoint、幂等、Retry、Cancel 和 Resume 正确。
- 可解释：结构化计划、事件、证据和错误可查看。
- 可验证：有 Golden Dataset、自动化评测和发布门禁。
- 可治理：有 Policy、Approval、Audit 和隐私控制。
- 可演进：与 V1.2 兼容，并为 V1.4 Workflow Engine 留出清晰接口。
