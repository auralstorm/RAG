# V2.0 — Enterprise-Grade Platform 开发包

> 日期：2026-11-24。状态：研发设计与实施计划草案；具体部署拓扑、容量/SLO、RPO/RTO 及制度在 M0 冻结。  
> 范围依据 [总体路线图 §5.6](../总体版本路线图与架构演进规划.md)，公共增量依据 [统一契约第 11 节](../../architecture/统一契约与跨版本演进规则.md)。设计完成不代表已达到生产指标或取得合规认证。

## 1. 产品边界

V2.0 将现有 RAG/Agent/Workflow 平台完善为长期可运营的企业基础设施：企业内部资源授权、高可用/容量、模型路由、额度与成本、企业安全/数据生命周期、质量/可观测/运营、备份/灾备及升级治理。

用户已确认所有版本采用单一企业内部部署，依据 [ADR-0013](../../adr/0013-single-enterprise-deployment-scope.md)。V2.0 复用企业身份、角色、KB/资源 ACL，按内部协作需求补充 Organization/Workspace；验收覆盖本企业多个用户与角色的资源权限。

## 2. 文档索引

| 文件 | 负责内容 |
|---|---|
| [01 组织与资源授权](01-organization-workspace-and-resource-authorization.md) | 可信身份、组织/成员与企业内资源授权 |
| [02 高可用与容量](02-high-availability-capacity-and-runtime-operations.md) | 故障域、冗余、队列/Worker、限流、伸缩和服务运营 |
| [03 模型与成本](03-model-routing-budget-quota-and-cost-governance.md) | 路由策略、多级额度预留、追加账本和账单对账 |
| [04 安全与生命周期](04-enterprise-security-compliance-and-data-lifecycle.md) | 密钥、授权、网络、数据分级、员工撤权/删除及安全事件 |
| [05 质量与运营](05-evaluation-observability-and-admin-operations.md) | 统一评测/门禁、SLO、漂移、审计、Admin/Workspace 运维 |
| [06 备份与灾备](06-backup-disaster-recovery-and-upgrade-governance.md) | Recovery Set、演练、外部效果核对、发布/回滚 |
| [07 数据库与 API](07-database-api-and-contract-design.md) | 新增表、原实体增量、状态、API/事件及兼容迁移 |
| [08 代码与 Backlog](08-code-structure-and-development-backlog.md) | 模块职责、任务 ID、优先级和依赖 |
| [09 实施与验收](09-complete-implementation-plan-and-acceptance.md) | M0–M8、生产准入、测试矩阵、生产签署与交付 |

先读本 README 和 09 的前置条件与验收，再读统一契约第 11 节及对应模块详设。公共字段/状态在统一契约管理，本版新增存储/API 只在 07 详列；按版本增量演进。

## 3. 依赖与复用

- V1.0–V1.2：可信身份/Policy、知识与模型 Gateway、不可变配置、Trace/Audit、Dataset/Profile/Runner/Gate。
- V1.3：Agent Run/Step/Checkpoint、预算/当前授权恢复及 HITL 契约；Multi-Agent 仍依业务收益准入，不是所有 V2.0 运营能力的前置条件。
- V1.4：Workflow、审批/Grant、Business Action、Trigger/Timer、UNKNOWN/补偿及真实工单试点的事实记录。

复用 PostgreSQL、Redis、RabbitMQ/Celery、Elasticsearch、S3-compatible 存储、OpenTelemetry/Phoenix 和现有 Model Gateway/RAGAS Adapter。代码目录、版本、云服务与部署命令依据实际仓库和 M0 环境确认；不默认迁移 Kubernetes、Kafka、新主数据库或全面微服务。

## 4. 范围与决策

P0 基础：企业内部权限/安全上下文、可验证授权、冗余与容量边界、模型能力/预算路由、持久用量/预留/对账、企业安全/生命周期、质量与运营、Recovery Set/外部效果恢复、迁移和生产 Runbook。

跨区域多活、复杂自动成本优化和额外认证根据业务需求作为条件/P1 投资，当前按单企业范围交付。

部署范围已由 ADR-0013 确认；预算与恢复的设计取舍见 [ADR-0011](../../adr/0011-budget-reservations-and-usage-ledger.md)、[ADR-0012](../../adr/0012-recovery-reconciliation-before-side-effects.md)，这两份草案仍待实际 POC 与架构评审。

## 5. 发布条件

满足全部 P0、真实 SLO/容量与恢复演练、预算/安全/质量门禁及业务签署。数据库恢复完成后仍须核对外部操作，内部估算与外部账单分别验收。

系统/云环境、目标用户/数据量、身份/组织映射、价格/计量来源、保留/法规要求、SLO/恢复指标尚未提供的细节列入 M0，允许完成可审阅设计与 Fake 验证，相关生产能力维持未验收状态。
