# V1.4 — Enterprise Workflow & Integration 开发包

> 日期：2026-11-23。状态：详细设计与研发计划草案，待 M0 接口/业务冻结及 POC。  
> 公共契约依据 [统一契约与跨版本演进规则](../../architecture/统一契约与跨版本演进规则.md)，版本范围依据 [总体路线图 §5.5](../总体版本路线图与架构演进规划.md)。文档完成不代表生产系统已接入或验收通过。

## 1. 目标与已确认场景

V1.4 在既有 Tool Gateway、Policy、Agent Registry、HITL 和评测底座上，交付生产 Connector、确定性 Workflow、Approval Center、事件/定时触发、业务写操作确认、补偿和审计。

用户已确认：单一企业内部部署；首个流程类型为 **工单创建→审批→结果确认**。本包将其展开为“平台内工单申请/草稿→审批→外部工单系统创建→结果确认”。草稿是平台数据，外部写入必须在对应参数获得批准之后执行。

具体工单平台、接口、审批人/组、超时与升级制度、可用补偿动作尚未提供，均进入 M0 冻结清单。本文的 `ticket_system`、Tool Key、字段及示例阈值是接口适配设计，不宣称任何真实厂商已经支持。

## 2. 文档索引与阅读顺序

| 文件 | 负责的设计 |
|---|---|
| [01 Workflow 执行架构](01-workflow-engine-and-execution-architecture.md) | 确定性定义、实例/步骤、调度、Agent 边界与示例流程 |
| [02 生产 Connector](02-production-connectors-and-integration-governance.md) | REST/SQL/MCP 适配、凭据、能力验收与生产准入 |
| [03 审批与业务动作](03-approval-center-and-business-action-governance.md) | 审批组/阶段/委托/升级、参数绑定及写操作授权 |
| [04 事件、定时与恢复](04-events-scheduling-compensation-and-recovery.md) | Webhook/Schedule、Outbox、UNKNOWN 对账、补偿与取消 |
| [05 Chat/Admin UX](05-chat-admin-workflow-and-connector-ux.md) | 工单申请、审批待办、实例运维、连接器管理与权限 |
| [06 数据库与 API](06-database-api-and-contract-design.md) | 本版新增表、既有实体增量、API、错误、事件、迁移 |
| [07 代码结构与 Backlog](07-code-structure-and-development-backlog.md) | 领域模块、接口职责、任务 ID、优先级与依赖 |
| [08 实施计划与验收](08-complete-implementation-plan-and-acceptance.md) | M0–M7、Entry/Exit、测试矩阵、试点及发布检查 |

新任务先读本 README、统一契约第 5/10 节和 08；按任务进入对应详设。01 管流程语义，06 管本版存储/API 增量；其余文件通过引用使用规范字段，不建立第二套实体或状态字典。

## 3. 依赖与复用

- V1.0：身份、KB/RAG、Model Gateway、基础审计、Trace、生命周期及部署。
- V1.1：Tool Registry/Gateway、Connector Adapter、可信身份、幂等及受控执行。
- V1.2：不可变发布快照、资源 Binding、Sandbox、Dataset/Profile/Runner/Gate。
- V1.3：现有 human_interactions/ApprovalRequest/Decision 与 Agent-Workflow 集成契约。基础 Workflow 不依赖 Planner 或 Multi-Agent 被启用；若上游范围经 ADR 裁剪，仍须验收其实际复用的最小能力。

复用已有 Agent Run、Tool Call、human_interactions、Policy、Audit、Evaluation。新增 Workflow Definition/Version/Instance/Step 和 Business Action，因为它们表达不同业务事实；不将 Workflow 状态写进 Agent Run，也不另建平行审批 ID 或评测系统。

## 4. 技术与范围基线

沿用 Python/FastAPI、React/TypeScript、PostgreSQL、Redis、RabbitMQ/Celery、S3/RustFS、OpenTelemetry/Phoenix、Tool Gateway、Model Gateway 和现有评测 Adapter。Workflow 的持久调度方案见 [ADR-0009](../../adr/0009-durable-workflow-and-shared-approval.md)，实施前用故障与长等待 POC 验证。

P0：受控声明式流程、版本发布、工单试点 Connector、Approval Center 最小审批组/分配/委托/升级/拒绝/撤回、可靠事件/定时器、结果对账、允许的补偿、业务审计、权限与恢复验收。

P1：更多 Connector、规则编辑体验、复杂报表和业务日历增强。V1.4 不预设通用 BPMN/任意代码 Designer、全部 HR/CRM/ERP 接入或跨地域多活。所有版本沿用单企业部署与企业内授权。

## 5. 发布边界

Mock 工单流程用于开发和确定性回归；生产验收必须有至少一个经业务负责人认可的真实工单流程，覆盖审批、写入、结果确认和审计。未冻结真实接口/审批制度时可完成通用实现与 Mock 验证，但不能将 Mock 结果签成 V1.4 生产通过。

未知提交状态进入对账/人工处理；应用版本回滚不能当作撤销外部业务操作。启用生产写入以 Connector、Tool、Workflow Version、Policy、审批和幂等能力共同准入，不凭单个开关开放。
