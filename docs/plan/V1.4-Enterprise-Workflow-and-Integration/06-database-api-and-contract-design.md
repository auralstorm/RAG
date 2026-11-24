# 06｜V1.4 数据库、API 与契约增量

> 状态：逻辑设计草案；物理 DDL 由实际 Alembic 制品确认。公共命名、状态和旧接口兼容依据 [统一契约第 10 节](../../architecture/统一契约与跨版本演进规则.md)。本文件是本版新增实体/API 的详细解释源，其他文件引用本清单。

## 1. 存储与字段约定

沿用 PostgreSQL 业务事实源、Redis 可重建缓存、RabbitMQ/Celery 派发及 S3-compatible 对象存储。ID 使用 UUID，时间使用 UTC timestamptz，稳定标识/状态为受控字符串，结构化小对象使用 JSONB，大正文/产物存受控引用。

单企业资源使用非空 deployment_namespace 和现有主体/组织 ACL；子表通过父对象执行资源授权。deployment_namespace 区分本企业的部署实例和环境，不改变资源 ID、业务幂等 Key 或授权规则。下列列表中的公共状态值均从统一契约读取，避免重述第二套枚举。

## 2. 新增 Workflow 实体

| 表 | 字段与约束 |
|---|---|
| workflow_definitions | id、deployment_namespace、workflow_key、name、description、owner_subject_id、visibility、status、current_version_id NULL、lock_version、created_at/updated_at；UNIQUE(namespace, workflow_key) |
| workflow_versions | id、workflow_id FK、version_number、schema_version、definition_json、definition_hash、binding_snapshot_json、validation_report、status、created_by、published_by/at NULL、created_at；UNIQUE(workflow_id, version_number)，发布内容不可变 |
| workflow_instances | id、deployment_namespace、workflow_key、workflow_version_id FK、requester_subject_id、business_key NULL、idempotency_key、request_hash、input_ref/output_ref NULL、status、terminal_reason NULL、deadline_at、origin_agent_run_id NULL、origin_trigger_event_id NULL、last_sequence_no、lock_version、started_at/finished_at NULL、created_at/updated_at |
| workflow_steps | id、instance_id FK、step_key、sequence_no、step_type、status、resolved_input_ref NULL、parameter_hash NULL、action_id NULL、approval_id NULL、result_ref NULL、attempt_count、deadline_at、lease_owner/lease_until NULL、fencing_token、created_at/updated_at；UNIQUE(instance_id, step_key) 与 UNIQUE(instance_id, sequence_no) |
| workflow_step_attempts | id、step_id FK、attempt_no、status、fencing_token、tool_call_id NULL、error_code/error_summary NULL、started_at/finished_at NULL、result_ref NULL；UNIQUE(step_id, attempt_no)，历史 Attempt 结果保留 |
| workflow_events | id、instance_id FK、sequence_no、event_type、schema_version、payload_json、correlation_id、created_at；UNIQUE(instance_id, sequence_no) |

实例创建唯一键为 `(deployment_namespace, requester_subject_id, workflow_key, idempotency_key)`，各列非空。规范 request_hash 包含原输入、明确版本/选择意图及配置；同 Key 变更输入/显式版本返回冲突，published 重试先查已有绑定。

Step 与 Action/Approval 引用允许启动前为空，在进入对应等待/执行状态时校验完整性。现有跨表引用由外键或等效约束保护，级联删除不能误删独立审计或已发生的外部效果。

## 3. Trigger、Timer 与 Business Action

| 表 | 字段与约束 |
|---|---|
| workflow_triggers | id、deployment_namespace、trigger_key、owner_subject_id、trigger_type、status、current_version_id、created_at/updated_at；UNIQUE(namespace, trigger_key) |
| workflow_trigger_versions | id、trigger_id FK、version_number、workflow_binding_json、source_identity_ref、config_json、schema_version、content_hash、created_at；UNIQUE(trigger_id, version_number) |
| workflow_trigger_events | id、trigger_id/version_id、source_key、source_event_id NULL、scheduled_for_utc NULL、payload_ref、payload_hash、status、instance_id NULL、received_at/processed_at NULL；UNIQUE(trigger_id, source_key) |
| durable_timers | id、owner_scope、instance_id NULL、approval_id NULL、purpose、timer_revision、due_at、status、lease_owner/lease_until、fencing_token、created_at/updated_at；CHECK 唯一合法 Owner，按各 Owner/purpose/revision 建部分唯一索引 |
| business_actions | id、deployment_namespace、execution_scope、run_id/agent_step_id NULL、workflow_instance_id/workflow_step_id NULL、tool_version_id、connector_instance_id、operation_key、parameter_hash、input_ref、status、external_operation_ref/external_resource_ref NULL、authorization_grant_ref NULL、compensates_action_id NULL、policy_decision_ref、started_at/finished_at NULL、created_at/updated_at |

Business Action DTO 的 action_id 映射到 business_actions.id，idempotency_key 映射 operation_key；UNIQUE(namespace, connector_instance_id, operation_key)，补偿有独立 Key 并关联原 Action。Action 是逻辑效果汇总，具体网络调用继续使用现有 tool_calls，避免重复调用日志系统。

Trigger 的 source_key 是稳定 `webhook:<source_event_id>` 或 `schedule:<scheduled_for_utc>` 等已冻结编码，禁止空值；同源 Key 不同 payload_hash 冲突。Timer 根据 Workflow Instance 或原 approval_id 归属，直接 Agent 审批升级也复用 durable_timers，不要求伪造 Workflow Instance。

## 4. Approval Center 新增与既有表增量

| 新表 | 字段与约束 |
|---|---|
| approval_policies / approval_policy_versions | 稳定 policy_key、Owner 与当前版本；版本保存阶段/组/回避/有效期/升级/委托规则、schema_version、Hash、发布元数据，不可变 |
| approval_stages | id、approval_id FK human_interactions、stage_key、sequence_no、policy_version_id、candidate_snapshot_json/hash、assignment_revision、mode、status、expires_at；UNIQUE(approval_id, stage_key) |
| approval_assignments | id、stage_id、approver_subject_id、assignment_revision、delegation_id NULL、status、assigned_at/expires_at；按当前阶段/主体/revision 唯一 |
| approval_stage_decisions | id、stage_id、assignment_revision、approver_subject_id、decision、reason、parameter_hash、idempotency_key、decided_at；UNIQUE(stage_id, assignment_revision, approver_subject_id) |
| approval_delegations | id、delegator_subject_id、delegate_subject_id、scope_json、valid_from/until、reason、status、created_at；记录有效委托，不改变真实身份 |
| approval_grants | id、approval_id、action_id、token_hash、binding_hash、valid_until、claimed_at/revoked_at NULL、status（ISSUED/CLAIMED/EXPIRED/REVOKED）、created_at；Token Hash 唯一，按 action_id WHERE status=CLAIMED 建部分唯一索引，历史 Grant 保留 |

human_interactions 增加 execution_scope、workflow_instance_id/workflow_step_id/action_id、approval_policy_version_id、current_stage_id；run_id/step_id 在 Workflow Scope 可空，Agent Scope 保持原语义。request/decision/expiry/Hash/ID 继续沿用，`decision_id` 生效唯一；阶段决定与最终决定分别记录。

Grant 使用时同时检查 CLAIMED 状态、valid_until、未撤回及当前 Policy。续期/重新审批在同事务将旧 Grant 标为 EXPIRED/REVOKED 后领取新的唯一 Grant；索引谓词不使用随时间变化的 now()，也不通过重复消费原 Token 延长授权。

现有 tool_calls 增加 execution_scope、workflow_instance_id/workflow_step_id/action_id、attempt_no、commit_state；保留 Agent 关联、参数摘要、幂等 Hash、Policy、Trace 和结束时间。Gateway 的执行域由受信服务传递，CHECK/领域校验保证 Owner 合法，不能接受客户端任意 Agent/Workflow 身份。

Connector 配置复用 connector_instances 及已有不可变配置；必要时增量 connector_config_versions、production_enablements、health/rotation 元数据，具体已有表先在 M0 合并。Role/Group 解析复用现有 Identity/Policy，不能凭示例重建用户和组织权威。

Evaluation 复用已有 datasets/profiles/runs/results：增加 target_type=workflow、workflow_version_id NULL、结果的 workflow_instance_id NULL 及指标 JSON；RAG/Agent 记录和运行 Gate 不变。Audit/Trace/Outbox 使用既有平台基础设施，Workflow events 用于实例重建，不替代独立业务审计。

## 5. 索引、事务与生命周期

高频索引：instances(status, created_at)、instances(requester_subject_id, created_at)、steps(status, lease_until)、events(instance_id, sequence_no)、timers(status, due_at)、actions(status, updated_at)、assignments(approver_subject_id, status, expires_at)、outbox(status, next_attempt_at)。外部引用和敏感字段按真实查询需求评估索引，JSONB 不无差别加 GIN。

创建/状态变化/审批决定/Grant Claim 与 Outbox、业务审计可靠记录同事务或平台可靠审计机制闭合。网络调用在事务外；领取租约使用 DB 当前时间、条件更新与 fencing_token，不能依靠进程内锁保证跨 Worker 互斥。

终态仍保留允许的业务审计、去重/外部引用和补偿事实。申请正文、附件、Trace 与个人身份映射按既有生命周期分别清理；实例等待/恢复中的必要数据不得无依据永久保留。具体保留期由 M0 制度和业务需求冻结。

## 6. API 清单

统一 `/api/v1`、可信主体、UTC 时间、分页与平台错误结构。写接口携带 Idempotency-Key，状态/配置变化携带 revision/If-Match 等乐观锁前提；Request ID/Trace ID 透传。

| 方法 | 路径 | 行为 |
|---|---|---|
| POST / GET | /api/v1/workflows | 创建定义 / 按权限列表 |
| GET / PATCH | /api/v1/workflows/{workflow_id} | 详情 / 元数据更新 |
| POST / GET | /api/v1/workflows/{workflow_id}/versions | 新草稿 / 版本列表 |
| GET / PATCH | /api/v1/workflow-versions/{version_id} | 详情 / 仅草稿内容更新 |
| POST | /api/v1/workflow-versions/{version_id}/validate | 静态/资源/回归校验 |
| POST | /api/v1/workflow-versions/{version_id}/publish | Gate 后原子发布 |
| POST | /api/v1/workflows/{workflow_id}/rollback | 新实例指针回滚 |
| POST | /api/v1/workflows/{workflow_id}/suspend | 停止接收新实例，按策略处理在途动作 |
| POST | /api/v1/workflows/{workflow_id}/resume | 当前发布版本/权限有效后恢复接收 |
| POST / GET | /api/v1/workflow-instances | 创建 / 授权范围列表 |
| GET | /api/v1/workflow-instances/{instance_id} | 状态、结果、效果摘要 |
| GET | /api/v1/workflow-instances/{instance_id}/steps | Step/Attempt 查询 |
| GET | /api/v1/workflow-instances/{instance_id}/events | JSON 游标事件补拉 |
| GET | /api/v1/workflow-instances/{instance_id}/stream | SSE，支持 Last-Event-ID |
| POST | /api/v1/workflow-instances/{instance_id}/pause | 安全边界暂停请求 |
| POST | /api/v1/workflow-instances/{instance_id}/resume | 当前授权与恢复前提检查 |
| POST | /api/v1/workflow-instances/{instance_id}/cancel | 请求取消，结果异步确认 |
| POST | /api/v1/business-actions/{action_id}/reconcile | 有证据的受控对账/回查命令 |
| POST | /api/v1/business-actions/{action_id}/compensate | 创建/复用补偿 Action，必要时审批 |
| GET | /api/v1/approvals | 当前可见的待办/历史请求视图 |
| GET | /api/v1/approvals/{approval_id} | 请求/阶段/分配/最终决定 |
| POST | /api/v1/approvals/{approval_id}/decisions | 统一决定服务 |
| POST | /api/v1/approvals/{approval_id}/reassign | 有制度依据的 Assignment revision 更新 |
| POST | /api/v1/approvals/{approval_id}/withdraw | 申请人/授权主体撤回；提交后按在途效果处理 |
| POST / GET | /api/v1/approval-delegations | 委托创建 / 授权列表 |
| POST | /api/v1/approval-delegations/{delegation_id}/revoke | 撤销未过期委托并审计 |
| POST / GET | /api/v1/approval-policies | 策略定义管理 |
| GET / PATCH | /api/v1/approval-policies/{policy_id} | 详情 / 治理元数据，不原地修改发布规则 |
| POST | /api/v1/approval-policies/{policy_id}/versions | 新不可变策略版本草稿 |
| GET | /api/v1/approval-policies/{policy_id}/versions | 策略版本列表 |
| GET / PATCH | /api/v1/approval-policy-versions/{version_id} | 详情 / 仅草稿规则编辑 |
| POST | /api/v1/approval-policy-versions/{version_id}/validate | 候选组、阶段、回避、时限与策略测试 |
| POST | /api/v1/approval-policy-versions/{version_id}/publish | 规则校验和策略测试后发布 |
| POST / GET | /api/v1/workflow-triggers | 受控事件/Schedule 注册与查询 |
| GET / PATCH | /api/v1/workflow-triggers/{trigger_id} | 详情 / 治理元数据 |
| POST / GET | /api/v1/workflow-triggers/{trigger_id}/versions | 新 Trigger 配置草稿 / 版本列表 |
| GET / PATCH | /api/v1/workflow-trigger-versions/{version_id} | 详情 / 仅草稿编辑 |
| POST | /api/v1/workflow-trigger-versions/{version_id}/validate | 来源、规则、Schema、时区与 Scope 校验 |
| POST | /api/v1/workflow-trigger-versions/{version_id}/publish | 原子启用新配置快照 |
| POST | /api/v1/workflow-triggers/{trigger_id}/enable | 来源/版本/身份/准入有效后启用 |
| POST | /api/v1/workflow-triggers/{trigger_id}/disable | 停用未来事件/发生 |
| POST | /api/v1/workflow-triggers/{trigger_id}/events | 来源校验后的事件受理 |
| POST | /api/v1/connectors/{connector_id}/production-enable | 依据准入证据启用允许实例/能力 |

Connector 列表、配置、health-check 和 tool-calls 查询复用旧接口；production-enable 中 connector_id 遵循现有 Connector 管理 ID，并在请求引用 connector_instance_id，避免 Definition/Instance 混同。Trigger 配置增加与 Workflow Version 同类的草稿/校验/发布元数据，旧已受理事件固定原快照；客户端使用 API，不直接读表。

工单创建请求示例（身份从服务端注入，字段需正式输入 Schema 校验）：

```json
{
  "workflow_key": "ticket.create_with_approval",
  "workflow_version": "published",
  "input": {
    "title": "示例工单申请",
    "description": "演示数据，非生产请求",
    "category": "it_support"
  }
}
```

返回 instance_id、status、固定 workflow_version_id、Trace ID；不是外部 ticket_id 或“已创建成功”。reconcile/decisions 的证据、revision、Hash 与 Owner 从实际资源检查，任意客户端 status 字段不作为状态迁移命令。

## 7. 权限与错误

| 动作 | Policy Action | Permission/附加条件 |
|---|---|---|
| 定义创建/编辑/测试/发布 | workflow.create/edit/test/publish | 组织创建权及对应资源 create/edit/test/publish；草稿/快照规则 |
| 启动/查看实例 | workflow.start/view | start/view + 原始用户、版本 Binding、实例归属 |
| 定义回滚/停用/恢复及实例暂停/取消/恢复 | workflow.rollback/suspend/resume_definition/pause/cancel/resume | operate + 当前状态；来源用户与运维能力分别判定 |
| 对账/补偿 | workflow.reconcile/compensate | reconcile/compensate + 证据、风险、当前资源授权和必要审批 |
| 查看/决定审批 | approval.view/decide | view/decide + Assignment/组/委托/回避/Hash/有效期 |
| 撤回/委托/分配/策略管理 | approval.withdraw/delegate/reassign/manage_policy/publish_policy | 相应管理权；申请归属、范围/制度/并发校验 |
| Trigger 管理/校验/发布/启停/事件受理 | workflow.trigger.manage/validate/publish/enable/disable/accept | 当前来源身份、Trigger Scope、版本和目标 Workflow 授权 |
| Connector 管理/生产启用 | connector.manage/production_enable | manage/production_enable + 实例 Scope/准入记录；不授予 tool.invoke |

错误至少区分 WORKFLOW_VERSION_UNAVAILABLE、DEFINITION_INVALID、IDEMPOTENCY_CONFLICT、REVISION_CONFLICT、APPROVAL_EXPIRED、APPROVAL_BINDING_MISMATCH、ACTION_OUTCOME_UNKNOWN、COMPENSATION_NOT_ALLOWED、CONNECTOR_NOT_PRODUCTION_READY、POLICY_DENIED。稳定 code 与 retryable 明确；UNKNOWN 不返回允许盲目重试的指示。

## 8. 事件与内部接口

规范事件：workflow.version.validated/published/rolled_back；workflow.instance.accepted/started/waiting_approval/waiting_event/paused/resumed/cancel_requested/cancelled/succeeded/failed/timed_out/needs_review；workflow.step.started/succeeded/failed/unknown；business.action.submitted/succeeded/failed/unknown/reconciled/compensated/compensation_failed；approval.requested/approved/rejected/expired/cancelled、approval.assignment.changed、approval.stage.decided。

只在对应事实事务提交后发结果事件；Stage 通过不发 approval.approved，最终请求通过才发。旧 Agent 的 run.* 与既有审批消费者保留适配，不将 Workflow 事件混入 Agent Run 序列。

内部接口使用平台类型：WorkflowRegistry.load_snapshot、WorkflowService.start/control、Scheduler.claim_due、StepExecutor.execute、BusinessActionService.prepare/submit/reconcile/compensate、ApprovalService.request/decide/claim_grant、TriggerService.accept、TimerService.schedule/claim。各模块通过接口关联，不跨模块直接写对方状态表。

## 9. 迁移与兼容验收

1. 盘点真实 users/主体、Tool Call、human_interactions、Outbox 与 Eval DDL，复用已有实体。
2. 新表/可空 Owner 列与 Scope 先 Expand；回填原 Agent 关联，无法归属的记录明确处理。
3. 新/旧接口部署兼容 Adapter，验证同一审批 ID、状态事实和去重语义。
4. 增量 Schema/OpenAPI/Event Diff 与数据引用/数量/Hash 校验通过后收紧 CHECK/唯一约束。
5. 灰度 Workflow/Connector/Scope；应用回滚保留兼容列和流程事实，不破坏性删除业务效果。

验收涵盖存量 Agent Run/Tool/审批/评测回归、直接 Workflow 无伪造 Agent 引用、重复事件/操作、并发审批/取消、UNKNOWN/补偿和删除留存。所有 OpenAPI、JSON Schema、迁移及测试制品在代码仓生成；本文件没有冒充已执行 DDL 或迁移。
