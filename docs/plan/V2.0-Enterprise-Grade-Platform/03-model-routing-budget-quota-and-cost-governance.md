# 03｜模型路由、预算、配额与成本治理

> 版本：V2.0。复用 Model Gateway/Model Profile 和 Run 预算，新增公共字段/状态见 [统一契约第 11 节](../../architecture/统一契约与跨版本演进规则.md)，账本/API 见 [07](07-database-api-and-contract-design.md)。方案记录于 ADR-0011。

## 1. 路由是受控选择

Route Policy 为不可变版本，候选 Profile/Provider 必须已授权且满足任务能力、上下文、输出上限、区域/驻留、格式、预算及当前可用性。顺序/权重/成本/延迟只在满足硬约束的候选内比较。

生成、Embedding、Rerank、Judge 等能力独立配置。Embedding 绑定索引的 embedding_config_hash/向量空间，不能因维度相同就切换模型；Judge/回归评测固定 Profile/Prompt/评分器，动态选择的不可比因素必须显式记录。

无合法候选时返回明确错误或按已配置策略排队，不回退到未授权模型/地区，不隐式扩大上下文、权限或预算。供应商能力和价格来自固定 Registry/POC，不能仅凭模型名称猜测。

```json
{
  "schema_version": "1.0",
  "route_key": "enterprise.chat.default",
  "required_capabilities": ["chat", "streaming"],
  "candidate_profile_version_ids": ["00000000-0000-4000-8000-000000000010", "00000000-0000-4000-8000-000000000011"],
  "fallback_max_attempts": 1,
  "budget_mode": "STRICT",
  "price_policy_ref": "approved_pricing_snapshot"
}
```

这是字段示例，候选和阈值需实际模型/地区/价格冻结。route_resolution_id 记录最终候选、版本、约束与原因；重试/fallback 是新的物理调用 Attempt，可能再次产生费用。

## 2. 多级限额

速率/并发限制按系统、Workspace/部门、用户、模型、Tool/Run/Workflow 逐级检查。Redis 可以快速计数，持久预算和用量在 PostgreSQL；缓存失效不让系统解除硬上限。

预算范围固定货币/周期或 Token/次数单位；父子范围共同约束。一次消费可关联多个预算约束，但全平台费用只记一次，不能把父子统计相加造成重复成本。跨货币比较使用已批准的价格/汇率快照及明确口径。

max_steps、max_total_tokens、Deadline 等既有 Run 预算继续生效；金额预留是新增约束，不替换旧预算、审批或 Policy。

## 3. 准入与预留

执行前固定路由/价格/请求上限，计算保守预留，在同事务锁定按稳定顺序排列的预算行，验证所有约束并创建 admission_id/reservation_id。可用额度 = 限额 − 已记费用 − 有效预留/待核对金额。

严格预算需要可靠的输入/输出/价格上界和供应商能力。未知价格/单位或缺少可验证的上限时严格模式拒绝该调用；不能以估算值承诺外部账单绝不超额。非严格预算模式须显式配置上限不确定性与告警，报告区分内部控制与供应商收费。

每个物理 Provider Attempt 关联独立 admission 与 source_attempt_id；重复网络消息不再次预留同一 Attempt。真正发生的重试/fallback 是独立消费，取得新预留后才能发出；已确认未发出的 Attempt 可按证据释放。

## 4. 用量账本与结算

UsageRecord 固定来源事件/Attempt、Workspace/主体引用、Run/Workflow/模型、路由/价格版本、输入/输出 Token、用量状态、金额/币种和时间。失败、超时、取消及流式部分输出也可能收费。

账本追加不可变 Entry，采用来源事件/版本唯一键去重；退款/修正写调整 Entry，不覆盖历史。NUMERIC/Decimal 表达金额，精度、舍入、税费/折扣/汇率与确认时点按计费源冻结。

| 调用事实 | 额度/账本处理 |
|---|---|
| 已确认未派发 | 释放预留并记录证据 |
| 已派发且有完整用量 | 追加用量，结算预留，差额按规则释放/调整 |
| 已派发但用量/账单未知 | 保留待核对预留，标记 HELD_REVIEW，不能因请求失败或 TTL 直接退款 |
| 供应商后续确认/修正 | 按同来源/版本追加结算或调整，记录旧账本关联 |

Stream 断线、Worker 失联和超时不能证明调用未执行。回收作业区分未派发与已派发未知；未知事实在对账/经授权的保守结算前占用额度，防止连续重试耗尽真实预算却显示余额充足。

## 5. 供应商账单与报告

对账核对 Provider Request/Attempt、模型/地区/时间、单位、实际价格及取消/失败收费。无法拿到逐请求账单时记录可核对粒度和未确认差异，不能补造精确费用。

Run/Step 的 token_usage_json/cost_estimate 保持兼容视图；费用权威来自版本化用量和 Ledger。在线仪表盘区分已确认费用、估算、预留和待核对；按部门/Agent/Workflow 汇总有明确分母和同一来源去重。

成本优化评估上下文/缓存、模型候选、批处理和评测隔离，但不能绕过 ACL、改变索引向量空间、放宽 Gate 或触发重复外部动作。历史 Agent/Workflow 固定快照，策略变化对新调用的生效范围明确记录。

## 6. 验收

覆盖并发争用多级额度、重复事件/结算、Decimal/多币种、流式取消、派发后崩溃、缺失 usage、价格变更、供应商对账差异、Redis/DB 故障及恢复后的预留。

路由负向测试确保能力/上下文/区域/授权/预算不合格候选被排除；Embedding/Judge 不因 fallback 破坏索引/评测一致性。严格准入验证已批准上界与数据库不超分配，报告同时注明外部实际账单的不确定因素。
