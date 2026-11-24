# 06 — V1.2 完整研发实施计划与阶段验收标准

> 公共字段、状态、事件、权限与迁移映射见 [统一契约与跨版本演进规则](../../architecture/统一契约与跨版本演进规则.md)；本文件描述本版能力及增量，具体实现须通过契约与升级验收。

## 1. 项目目标

V1.2 的最终交付不是几个管理页面，而是一条可工作的 Agent 开发闭环：

```text
创建 Agent
  -> 配置 Definition / Prompt / Model / KB / Tools / Memory
  -> Playground 调试
  -> 创建或选择 Dataset
  -> 执行 Evaluation
  -> 通过 Release Gate
  -> 发布不可变 Agent Version
  -> Chat 授权使用
  -> Trace 观察与问题定位
  -> 必要时回滚
```

必须沿用 V1.0/V1.1 已确定的技术基线。若 V1.1 的 Runtime / Tool / Memory Contract 尚未验收，V1.2 不得通过复制实现来绕开依赖，应先补齐上游缺口。

## 2. 进入条件（Entry Criteria）

- V1.0 Standard RAG 主链路可用，Retriever Contract 稳定。
- V1.1 Agent Runtime 可通过 Facade 创建和执行 Run。
- V1.1 Tool Gateway 强制执行 Policy Engine。
- Memory / Context / Checkpoint 基础能力可调用。
- Model Gateway 有统一 Model Profile。
- Trace / Audit / RBAC 可复用。
- RabbitMQ / Celery / Redis / PostgreSQL / Object Storage 环境可用。
- 已建立 V1.2 需求基线、负责人和 ADR 流程。

若以上任一核心依赖未达标，应先做依赖补齐 Sprint，并更新计划。

## 3. 阶段划分

以下为建议的 8 个阶段。团队可按实际人力并行，但不得跳过阶段 Exit Criteria。周期由团队规模、任务估算和 V1.1 实际完成度确认；本文件以里程碑验收管理，尚无固定周数承诺。

### Phase 0 — 依赖盘点与架构冻结

工作：
- 对照 V1.1 Runtime、Tool Gateway、Memory、Policy、Trace Contract。
- 定义 Agent Definition Schema v1。
- 确定 Agent / Version / Prompt / Dataset / Evaluation / Release 领域模型。
- 明确 Playground Sandbox 安全模型。
- 确认角色权限矩阵和数据生命周期。
- 形成 ADR：Definition Schema、Version Snapshot、Evaluation Runner、Release Gate。

交付物：
- Architecture Decision Records
- Contract OpenAPI / JSON Schema 初稿
- 数据库 ERD
- V1.2 Backlog 与依赖图

Exit Criteria：
- 核心 Contract 经评审冻结；字段/事件/权限采用统一契约规范，V1.1 Definition/Run 和 V1.0 eval_* 有显式映射与升级验证方案。
- 无未解决的高危权限绕过设计。
- 每个 P0 Epic 有 Owner 和验收定义。

### Phase 1 — Agent Registry 与 Definition

工作：
- 数据库迁移和领域模型。
- Agent CRUD、权限、可见范围。
- Definition Schema 校验。
- Definition Migration Framework。
- Draft Version、乐观锁和快照构建。
- 资源引用和反向引用检查。

交付物：
- Agent Registry API
- Agent Definition Schema
- 数据库迁移
- 单元、集成和权限测试

Exit Criteria：
- 可创建和编辑 Draft Agent。
- 非法 Definition 无法保存或进入发布流程。
- 越权资源引用被拒绝。
- Draft 与已发布版本严格分离。
- Schema 版本可追踪。

### Phase 2 — Prompt Management 与 Binding

工作：
- Prompt / Prompt Version。
- 模板变量 Schema、渲染、预览、Diff。
- Model / KB / Tool / Memory / Guardrail Binding。
- Binding Validator 与 Snapshot。
- 高风险 Tool 的生产绑定规则。

交付物：
- Prompt API / UI
- Binding Service
- Snapshot Builder 扩展
- Contract 测试

Exit Criteria：
- Prompt 版本不可变。
- Agent Version 可固定引用 Prompt 和资源版本。
- 未授权资源无法绑定。
- Definition 不包含秘密。
- 缺审批策略的生产写操作无法通过验证。

### Phase 3 — Agent Builder Admin UI

工作：
- Agent 列表和创建向导。
- Agent 编辑器各配置分区。
- 版本历史和差异。
- 角色权限、空态、错误态和保存反馈。
- 高级 Definition 查看模式。

交付物：
- Admin Agent Builder
- E2E 测试
- 前后端权限一致性报告

Exit Criteria：
- 开发者无需手工调用 API 即可创建、配置和保存 Draft。
- 表单字段与服务端 Schema 一致。
- 无权用户不能通过 API 越权操作。
- 配置变更有版本和审计记录。

### Phase 4 — Playground 与 Sandbox

工作：
- Playground Session / Run API。
- Runtime Facade 集成。
- Sandbox Policy 和 Mock Tool。
- SSE 事件与 Run 查询恢复。
- Debug Detail Aggregator。
- Token / Cost / Concurrency 限额。
- Playground UI。

交付物：
- Playground
- Sandbox Policy
- 调试 Trace 页面
- 安全测试报告

Exit Criteria：
- 可使用 Draft Agent 完成一次完整测试运行。
- 能查看 Prompt、Retrieval、Tool、Policy、Context、Model 关键事件。
- 断线后能按 Run ID 恢复查看。
- 生产写操作默认阻断。
- Playground 身份权限不高于操作者授权范围。
- 配额和超时限制生效。

### Phase 5 — Evaluation Framework

工作：
- Dataset / Case / Profile 版本化。
- Evaluation Job、Celery Worker。
- Agent Runtime Runner Adapter。
- Deterministic Scorer。
- P0 最小 Semantic Scorer 与适用的 RAGAS Adapter；额外 Judge/校准为 P1。
- 逐样本结果、Trace、报告。
- Version Compare 和取消/重试。
- Evaluation UI。

交付物：
- Evaluation API / Worker
- Dataset 管理和报告 UI
- 初始 Golden / Adversarial Dataset
- 指标定义文档、评分器版本/映射及异常处理记录

Exit Criteria：
- 可针对指定 Agent Version 和 Dataset Version 执行评测。
- 结果可追溯到固定配置。
- 确定性断言可重复执行；至少一种语义评分通过，适用 RAGAS 指标可追溯到固定 Profile/Scorer 版本。
- 必选评分器缺分、失败或未执行时，对应 Gate 不得通过。
- 评测与在线流量资源隔离。
- 取消、超时、重试和失败恢复符合预期。
- 报告包含逐样本失败原因和 Trace。

### Phase 6 — Release Governance 与 Chat 集成

工作：
- 发布前 Definition / Binding / Policy 校验。
- Evaluation Gate。
- 原子发布与并发控制。
- 发布历史、暂停、恢复、回滚。
- Chat Agent 目录与已发布版本调用。
- Run 版本固定和 Trace 链接。

交付物：
- Release API / UI
- Gate Policy
- Chat Agent 使用入口
- 回滚演练记录

Exit Criteria：
- 未通过硬门禁的版本不能发布。
- 发布切换原子化，运行中 Run 不受版本切换影响。
- 回滚可恢复历史版本且审计完整。
- Chat 只暴露用户有权访问的已发布 Agent。
- Draft Agent 无法被普通员工调用。

### Phase 7 — 系统验证、试点与发布

工作：
- 完整回归、权限矩阵、安全测试。
- 性能、成本和容量测试。
- 数据迁移与升级演练。
- 备份恢复、Worker 故障恢复。
- 试点 Agent：HR Knowledge Assistant、IT Helpdesk Knowledge Assistant（仅使用 Mock / 已授权只读资源）。
- 用户验收、文档和培训。
- 生产发布与观察。

交付物：
- 测试报告
- UAT 签署
- 发布 Runbook
- 回滚 Runbook
- 已发布示例 Agent
- 版本发布说明

Exit Criteria：
- P0 缺陷清零。
- 安全门禁通过。
- 发布与回滚演练通过。
- 核心 SLO 达到项目基线。
- 关键指标和告警已配置。
- 业务 Owner、平台 Owner 和安全负责人完成验收。

## 4. 跨团队工作流

建议工作流并行：
- Backend：Registry、Definition、Prompt、Evaluation、Release。
- Frontend：Builder、Playground、Evaluation、Release UI。
- Platform：Worker、队列、配额、部署、监控。
- Security：Policy、Sandbox、权限矩阵、数据治理。
- QA：Contract、E2E、回归、安全和性能。
- Product / Business：示例 Agent、Golden Dataset、UAT。

每个接口先定义 Contract，再并行开发。前后端使用 Mock Server / Fixture，避免等待完整后端后才开始 UI。

## 5. 关键里程碑

| 里程碑 | 完成定义 |
|---|---|
| M1 Definition Frozen | Schema、ERD、API Contract 评审通过 |
| M2 Agent Configurable | Registry、Prompt、Binding 可用 |
| M3 Agent Debuggable | Playground + Sandbox 通过 |
| M4 Agent Testable | Dataset、Evaluation、Report 可用 |
| M5 Agent Releasable | Gate、发布、回滚可用 |
| M6 V1.2 Production Ready | Chat 集成、权限、安全、运维验收通过 |

## 6. 测试验收矩阵

| 类别 | 必测场景 | 通过条件 |
|---|---|---|
| Definition | 缺字段、未知字段、越界值、错误引用 | 服务端拒绝并给出字段级错误 |
| Version | Draft 修改、Published 修改、并发发布 | Published 不可变，冲突可检测 |
| Prompt | 缺变量、恶意输入、敏感变量 | 安全渲染，不泄漏秘密 |
| Binding | 未授权 Tool / KB / Model | 保存或发布被拒绝 |
| Runtime | Run 期间切换版本 | Run 继续使用原版本 |
| Sandbox | 尝试生产写操作 | 默认阻断并审计 |
| Evaluation | Worker 重启、重复消息、取消 | 幂等、可恢复、无重复副作用 |
| Gate | 安全门禁失败、质量门禁失败 | 硬门禁阻断发布 |
| Release | 并发发布、回滚 | 原子切换，审计完整 |
| Chat | 用户无权访问 Agent | 不展示且 API 拒绝 |
| Privacy | Trace / Dataset 含敏感数据 | 按策略脱敏和生命周期处理 |
| Performance | 多用户 Playground + Evaluation | 在线流量不被评测任务挤占 |

## 7. 非功能验收

项目团队应在 Phase 0 建立真实基线。至少覆盖：
- API P95 / P99 延迟。
- Agent Run 成功率、超时率。
- Playground 并发数和资源上限。
- Evaluation 吞吐、队列等待时间。
- Token / 成本预算。
- 发布耗时。
- SSE 断线恢复。
- 数据库连接池和 Worker 资源饱和度。

不能在没有压测数据时宣称达到某个固定并发数或延迟目标。验收报告需记录测试环境、模型、数据集、并发模式和统计口径。

## 8. 发布与回滚策略

发布：
1. 部署兼容版本。
2. 执行数据库 Expand Migration。
3. 部署 API / Worker / Frontend。
4. 执行 Smoke / Contract / 权限测试。
5. 选择 Agent Version 并执行 Gate。
6. 发布指针原子切换。
7. 观察错误率、延迟、成本和 Tool Policy Deny。

回滚：
- Agent 行为回滚：切回已验证的历史 Agent Version。
- 应用回滚：回退应用镜像，但保留兼容数据库结构。
- 数据库回滚：优先采用前向修复；禁止未经验证的破坏性降级。
- 对已执行外部副作用不能假设版本回滚可以撤销业务操作。

## 9. 生产运维 Runbook 必备项

- Agent 暂停与恢复。
- 发布失败定位。
- 评测队列堆积处理。
- Worker 崩溃和重复任务处理。
- Model Provider 异常和配额耗尽。
- Tool Connector 不可用。
- Prompt / Definition 紧急回滚。
- Trace 查询和隐私高危溯源。
- Dataset / Report 删除和保留策略。
- 密钥轮换和权限撤销。

## 10. 最终验收签署

V1.2 发布需由以下责任方确认：
- Product Owner：业务流程和 UX。
- Platform / Backend Owner：架构、数据、API、运行稳定性。
- Security Owner：Policy、Sandbox、隐私、审计。
- QA Owner：测试覆盖和缺陷状态。
- Operations Owner：部署、告警、备份、恢复和 Runbook。
- Agent Owner：示例 Agent 质量与业务验收。

## 11. V1.2 最终 Definition of Done

- Agent 从创建到发布的完整闭环可用。
- 无需修改平台核心 Runtime 即可配置至少两个示例 Agent。
- 每个生产 Run 固定 Agent Version。
- Prompt、Tool、KB、Model、Memory 和 Guardrail 有版本化引用。
- Playground 与 Production 有服务端隔离。
- Evaluation 有版本化 Dataset、可追溯报告和发布 Gate。
- 发布、暂停、回滚和审计完整。
- RBAC / Policy Engine 不存在已知绕过路径。
- P0 测试、安全测试和 UAT 全部通过。
- 文档、API、Schema、运维手册与实现保持一致。
