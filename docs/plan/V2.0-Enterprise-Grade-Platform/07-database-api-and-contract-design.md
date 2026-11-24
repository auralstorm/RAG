# 07｜V2.0 数据库、API 与契约增量

> 逻辑设计草案，物理 DDL 以实际 Alembic 为准。公共命名/状态见 [统一契约第 11 节](../../architecture/统一契约与跨版本演进规则.md)。本文件是 V2.0 新增表/API 的详细解释源，复用既有业务事实与生成制品。

## 1. 基线与企业内部授权

ID/外部 Key/版本快照保持；UTC 时间、受控 Schema、Decimal/NUMERIC 金额和小对象 JSONB 沿用基线。资源继续按 Owner、用户/角色/KB ACL 及可信父对象授权，部署 namespace 区分实例和环境。

组织、Workspace 与成员复用已有 Identity/Policy；新增清单只补齐实际缺项，不能在 V2.0 重建平行身份服务。平台使用的企业供应商账号与凭据按明确服务身份、资源范围及费用权限访问，普通用户不获得全部账单或明文 Secret。

## 2. Organization、Workspace 与成员

| 表/增量 | 字段/约束 |
|---|---|
| organizations | id、organization_key、parent_id NULL、name、status；Key 在本部署唯一，parent_id 指本企业组织；变更父关系验证无循环及当前管理权 |
| workspaces | id、organization_id NULL、workspace_key、name、status、policy_ref、created_at/updated_at；workspace_key 在本部署唯一，组织绑定验证当前权限 |
| workspace_memberships | id、workspace_id、subject_id、role/binding_ref、status、valid_from/until、created_at；UNIQUE(workspace_id, subject_id)，角色组合走既有绑定；当前有效性独立于旧 Token |

旧资源按现有 Owner/KB/父对象 ACL 继续访问，按协作需求选择增加 organization_id/workspace_id，未关联 Workspace 不代表公共资源。组织成员与资源 ACL 分别校验，所有写路径验证关系目标的当前授权。

Run、Workflow、Approval、Action、Trigger、Timer、KB/版本/Chunk、Object/Trace/Eval/费用沿用原授权及稳定 ID/Key。新增关联按普通兼容迁移验证消费者、数量/Hash/引用与授权，不新增客户归属迁移表或全量回填阶段。

## 3. 路由、预算与用量账本

| 表 | 字段/约束 |
|---|---|
| model_route_policies / model_route_policy_versions | 稳定 route_key、Scope/Owner/发布指针；版本保存候选/能力/地区/预算/质量/重试规则、schema_version、Hash，不可变 |
| model_route_resolutions | id、scope、request_ref、policy_version_id、profile_version_id、decision_summary、price_version_ref、created_at；解释一次实际选择 |
| pricing_snapshots | id、provider/account/profile_ref、currency、unit_rate_json、validity、source_ref/hash、revision；价格/单位来源与版本可追溯，不存明文 Secret |
| budgets | id、workspace_id NULL、scope_type/id、unit/currency、period_start/end、limit_value、policy_version、lock_version、created_at/updated_at；相同范围/周期/单位唯一 |
| budget_reservations | id、admission_id、source_attempt_id、deployment_namespace、workspace_id NULL、route_resolution_id、price_version_ref、reserved_amount/units、dispatch_state、status、expires_at、evidence_ref、created_at/updated_at；UNIQUE(deployment_namespace, source_attempt_id) |
| budget_reservation_links | reservation_id、budget_id、reserved_value、unit/currency；多级约束关联，UNIQUE(reservation_id, budget_id) |
| usage_records | id、source_event_id、source_attempt_id、scope、provider_request_ref、Run/Workflow/模型引用、route/price_version、Token/计量单位、confirmation_state、source_ref/hash、revision、occurred_at；来源/版本去重 |
| cost_ledger_entries | id、usage_id/reservation_id NULL、scope、source_charge_key/revision、entry_kind、amount_delta/currency、adjusts_entry_id NULL、occurred_at；追加 CHARGE/CREDIT/ADJUSTMENT，稳定收费来源/版本/种类唯一 |
| cost_reconciliation_runs | id、scope、source_account_ref、source_manifest_ref/hash、policy_version、status、result/evidence_ref、started_at/finished_at；持久化一批对账事实，复用既有任务派发而不以 MQ 消息作为结果事实 |

DTO budget_id/reservation_id/usage_id/entry_id 映射各表 id；作用于多个预算的同一消费全平台只记一份 Ledger Entry，报表不能把 Budget Links 加总成新费用。金额/用量/汇率/舍入和来源粒度在 Adapter/价格策略冻结，缺失来源不能生成新的随机收费 Key 来规避去重。

预留准入按稳定 budget_id 顺序锁定全部约束，同事务校验/分配；结算/调整与余额视图同事务/可验证重建。RESERVED 过期只有确认未派发才能释放；DISPATCHED/HELD_REVIEW 保留到证据核对，恢复不能直接删除未知金额。

## 4. 安全、生命周期与运营

| 表/增量 | 内容与复用 |
|---|---|
| security_incidents | id、scope、severity、status、owner_subject_id、evidence_refs、containment/recovery_refs、created_at/updated_at/closed_at |
| legal_holds | id、scope/target_refs、basis、owner_subject_id、review/expiry、status；有限范围和依据，删除程序独立核对 |
| deletion_plans | id、scope、target_manifest_ref、policy_version、hold_refs、approval_ref、verification_ref；执行 Job 复用现有 lifecycle_jobs，增量映射公共状态与子项结果 |
| slo_definitions / slo_versions | 稳定目标、Owner；指标窗口/分母/成功/延迟/容量/环境与版本、Hash和审批依据 |
| runtime_capacity_policies | Scope/执行池/Provider、速率/并发/队列与扩缩容规则版本、Owner；实际状态依据已有租约/队列，不另造业务状态源 |

Model/Connector/Secret、Identity/Policy、审计、Agent/Workflow/审批/Action 与 Outbox 复用既有表，增加 Owner 上下文/路由/admission/journal/epoch 引用及兼容映射。价格、Operator 和审批 ID 不从 Prompt 参数可信化。

Evaluation 增加资源/Workspace、route/price/environment/恢复快照和受控 platform Adapter，保持 RAG/Agent/Workflow 原目标与 Gate。Trace/Metrics/Audit 仅加适用关联，不建立另一套评测或审计日志。

## 5. 恢复实体

| 表 | 字段/约束 |
|---|---|
| recovery_sets | id、scope、manifest_ref/hash、DB/WAL/object/config/key/journal_bounds、status、captured_at、verified_at；制品/覆盖可验证 |
| recovery_runs | id、recovery_set_id、scope、deployment_epoch、status、target_goals、verification/reconciliation_refs、started_at/finished_at |
| recovery_verifications | id、recovery_run_id、check_type、scope、result、evidence_ref/hash、created_at；具体恢复范围/外部事实/费用检查 |
| deployment_control_gates | id、scope、deployment_epoch、access_mode、approval/evidence_refs、lock_version、created_at/updated_at；同一范围唯一当前 Gate，敏感准入检查当前状态 |
| side_effect_journal_receipts | id、scope、source_operation_ref、original_key_hash、intent/confirmation_ref、content_hash、durability_policy_ref、receipt_ref、created_at；独立 Journal 的目录/凭证，不把仅 DB 副本当灾备证据 |

Journal 的加密外部记录保留原 Action/admission/Attempt 与 Key/输入引用；最小记录不复制敏感正文，恢复内容完整性/密钥/故障域与保留均须验证。旧 DB Key 和 Ledger 丢失窗口按外部证据恢复后放行，新的 deployment_epoch 不能替换业务 operation_key。

## 6. API 与授权

沿用 `/api/v1`、服务端资源授权、幂等写入、revision/If-Match、UTC、平台错误与审计。组织/成员接口复用现有能力并补齐缺项，查询只返回当前主体已授权资源。

| 方法 | 路径 | 行为 |
|---|---|---|
| GET / POST | /api/v1/organizations | 本企业授权组织目录 / 当前范围创建 |
| GET / PATCH | /api/v1/organizations/{organization_id} | 详情 / 元数据更新 |
| GET / POST | /api/v1/workspaces | 当前授权协作目录 / 创建 |
| GET / PATCH | /api/v1/workspaces/{workspace_id} | 详情 / 协作元数据更新 |
| GET / POST | /api/v1/workspaces/{workspace_id}/memberships | 受控成员查询 / 授权绑定 |
| POST | /api/v1/workspace-memberships/{membership_id}/revoke | 撤销成员并使当前授权失效 |
| GET / POST | /api/v1/model-route-policies | 策略查询 / 定义创建 |
| GET / PATCH | /api/v1/model-route-policies/{policy_id} | 详情 / 治理元数据 |
| GET / POST | /api/v1/model-route-policies/{policy_id}/versions | 不可变版本列表 / 草稿 |
| GET / PATCH | /api/v1/model-route-policy-versions/{version_id} | 查看 / 仅草稿内容 |
| POST | /api/v1/model-route-policy-versions/{version_id}/validate | 候选/能力/范围/价格/质量检查 |
| POST | /api/v1/model-route-policy-versions/{version_id}/publish | Gate 后原子发布 |
| GET / POST | /api/v1/pricing-snapshots | 授权价格元数据 / 有来源证据的不可变价格快照 |
| GET | /api/v1/pricing-snapshots/{snapshot_id} | 价格/单位/有效期与来源，凭据不返回 |
| GET / POST | /api/v1/budgets | 当前 Scope 额度查询 / 管理创建 |
| GET / PATCH | /api/v1/budgets/{budget_id} | 详情 / 审计限额调整，不重置已用/预留 |
| GET | /api/v1/budget-reservations/{reservation_id} | 授权预留/待核对视图 |
| POST | /api/v1/budget-reservations/{reservation_id}/reconcile | 按证据核对，不直接任意返还 |
| GET | /api/v1/usage-records | 授权用量/来源查询 |
| GET | /api/v1/cost-ledger-entries | 已确认/估算/调整账目视图 |
| POST | /api/v1/cost-reconciliations | 受控账单对账任务，归属/来源/版本验证 |
| GET | /api/v1/cost-reconciliations/{reconciliation_id} | 对账 Run 的结果/证据视图 |
| GET / POST | /api/v1/security-incidents | 当前范围查询 / 安全事件登记 |
| GET / PATCH | /api/v1/security-incidents/{incident_id} | 详情 / Owner/证据元数据 |
| POST | /api/v1/security-incidents/{incident_id}/transitions | 校验处置阶段与证据 |
| GET / POST | /api/v1/legal-holds | 授权保留查询 / 有依据的创建 |
| POST | /api/v1/legal-holds/{hold_id}/release | 复审/依据满足后解除，保留审计 |
| GET / POST | /api/v1/deletion-plans | 删除计划查询 / 受控申请 |
| POST | /api/v1/deletion-plans/{plan_id}/execute | 复用生命周期执行服务 |
| POST | /api/v1/deletion-plans/{plan_id}/verify | 子项/访问/恢复标记验证 |
| GET / POST | /api/v1/slo-definitions | 查询 / 经业务确认的定义 |
| GET / PATCH | /api/v1/slo-definitions/{slo_id} | 详情 / 治理元数据，不重写历史统计版本 |
| GET / POST | /api/v1/slo-definitions/{slo_id}/versions | 版本 / 新统计配置草稿 |
| GET / PATCH | /api/v1/slo-versions/{version_id} | 查看 / 仅草稿配置编辑 |
| POST | /api/v1/slo-versions/{version_id}/validate | 指标/窗口/分母/环境/Owner/可比性校验 |
| POST | /api/v1/slo-versions/{version_id}/publish | 可比口径/Owner 校验后发布 |
| GET / POST | /api/v1/capacity-policies | 当前容量配置 / 受控策略创建 |
| GET / PATCH | /api/v1/capacity-policies/{policy_id} | 详情 / 版本化规则更新与审计 |
| GET / POST | /api/v1/recovery-sets | 目录 / 创建受控捕获计划 |
| POST | /api/v1/recovery-sets/{set_id}/verify | 验证 Manifest/依赖/覆盖 |
| GET / POST | /api/v1/recovery-runs | 查看 / 创建隔离恢复或演练 |
| GET | /api/v1/recovery-runs/{recovery_id} | 阶段/已验证范围/证据 |
| POST | /api/v1/recovery-runs/{recovery_id}/release-read | 只读范围准入 |
| POST | /api/v1/recovery-runs/{recovery_id}/release-write | 外部事实/费用/授权闭合后放行 |
| GET | /api/v1/deployment-control-gates | 授权查看当前 Scope/Epoch/Gate |

SLO/路由版本详情、草稿、校验和发布复用同类版本治理服务并纳入 UI 联调。admission、Journal 写入、账本结算、Secret/Token 解密为受信内部接口，普通客户端不能提交虚假使用量/批准/有效身份。

```json
{
  "scope_type": "workspace",
  "scope_id": "00000000-0000-4000-8000-000000000001",
  "unit": "currency",
  "currency": "USD",
  "limit_value": "1000.00",
  "period_start": "2026-12-01T00:00:00Z",
  "period_end": "2027-01-01T00:00:00Z"
}
```

这是额度字段示例，币种/金额/时间不是业务承诺；Owner 从当前身份与资源授权解析，Decimal 字符串按正式 Schema 校验。

| 操作类别 | Policy/权限规则 |
|---|---|
| 组织/Workspace/成员 | organization.view/manage 或 workspace.view/manage/membership_manage + 当前组织、成员和资源授权 |
| 路由/价格/额度 | model.route.manage/publish、cost.price.manage、budget.manage + 当前资源与版本 Gate，不授予 Secret 读取 |
| 用量/对账 | cost.view/reconcile + 归属、来源与证据，调整不改历史 Entry |
| 事件/保留/删除 | security.incident.manage、data.hold/manage/delete/verify + 目的/制度/范围与当前授权 |
| SLO/容量 | operations.slo.manage、operations.capacity.manage + 真实范围/目标与审计 |
| 恢复/放行 | recovery.manage/verify/release + 新 Epoch、当前范围及完整恢复证据，读/写分开 |

## 7. 事件、错误与迁移

事件沿用平台 Envelope，按事实发送 workspace.membership.changed、model.route.published、budget.reserved/settled/released/review_required、usage.recorded/adjusted、security.incident.changed、data.deletion.partial/verified、recovery.set.verified、recovery.run.reconciling/completed、deployment.gate.changed。含 Owner/版本引用、correlation_id，不携明文 Secret/完整个人数据。

错误区分 AUTH_CONTEXT_REQUIRED、RESOURCE_SCOPE_MISMATCH、ROUTE_CONSTRAINT_UNSATISFIED、BUDGET_EXHAUSTED、PRICE_BOUND_UNKNOWN、USAGE_OUTCOME_UNKNOWN、RECOVERY_GATE_BLOCKED、RECOVERY_EVIDENCE_INCOMPLETE 和既有 Policy/幂等/revision 错误。retryable 反映安全性，未知费用/副作用不指示盲重放。

迁移：盘点实际实体/Owner/Unique/Key → 必要新表或可空协作/路由/预算/恢复引用 Expand → 兼容 API/消费者与原授权 → 数量/Hash/引用/权限/账目/恢复核验 → 收紧已验证约束并结束兼容窗口。Run/Step/Workflow/Approval/Action/Eval 和旧 Key 保持；供应商费用与外部操作不因迁移回滚消失。

检查旧客户端/运行/审批/队列、跨 Scope 关系、并发预留/结算、独立 Journal、PITR 后在途操作/费用与删除标记。新 OpenAPI/Event Schema/Migration 由代码仓生成并真实验收，本文不当作已经实施的 DDL。
