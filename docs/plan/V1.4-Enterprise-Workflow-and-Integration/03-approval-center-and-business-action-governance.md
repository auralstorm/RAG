# 03｜Approval Center 与业务动作治理

> 版本：V1.4。最小请求/决定沿用 [统一契约第 5/10 节](../../architecture/统一契约与跨版本演进规则.md)，数据库/API 增量见 [06](06-database-api-and-contract-design.md)。

## 1. 本版扩展边界

Approval Center 增加审批策略版本、审批阶段、审批人/组分配、授权委托、升级、拒绝和撤回，承接 V1.3 的 human_interactions。Approval Request 与外部动作共享明确绑定；Workflow Instance、Agent Run 和审批决定分别管理。

同一 approval_id 是同一待决事项；decision_id 是一次被可靠记录的决定。新增 Assignment/Stage/Policy 表表达流程责任，不另建与 human_interactions 冲突的审批主记录。

工单申请提交后，平台创建准备执行的 Business Action 和最终参数快照，再发起 approval；审批通过后才向外部工单系统写入。查看/评论申请与批准业务动作是不同权限。

## 2. 执行域与参数绑定

V1.4 为 ApprovalRequest 增加 execution_scope=agent/workflow，默认保持旧 Agent 语义；Workflow 请求新增 workflow_instance_id/workflow_step_id/action_id，Agent 请求继续使用 run_id/step_id。每项请求只有一个执行 Owner，来源 Agent 另存 origin_agent_run_id，不能为了填旧字段伪造 Agent Run。

现有 request/decision 字段、ID、Hash、有效期和审计保持。旧内部 approval-result 只处理其授权的 Agent 请求；Workflow 决定走统一决定服务再通知对应 Owner，不能把 Workflow 决定转成 Agent 恢复命令。

parameter_hash 由服务端对最终 Tool Version、Connector 配置、目标资源及实际写入参数规范化生成。Prompt、用户或审批页面不能提交任意“已验证 Hash”；批准后执行引用原解析快照，参数/绑定/有效权限变化使原批准失效。

## 3. 审批策略与阶段

策略版本固定步骤序列、组/角色解析方式、审批方式、拒绝规则、申请人回避、有效期、升级和委托范围。工单试点具体组名、审批时限、升级人和可撤回阶段尚待业务 M0 冻结；示例不替代企业制度。

| 策略方式 | V1.4 最小语义 |
|---|---|
| 单人 | 指定候选中一名当前有效审批人决定 |
| 审批组 any | 一个有效 Assignment 批准即可通过本阶段；任一拒绝按策略终止 |
| 审批组 all | 已固定候选集合全部批准才通过；任一拒绝终止；无有效候选时暂停并交人工处理 |
| 多阶段串行 | 当前阶段通过后创建下一阶段；全阶段通过才产生请求级 approved |

P0 至少实现单人、组 any/all 和串行阶段的受控配置及确定性测试；任意复杂审批表达式和通用流程 Designer 可后续扩展。候选集合在阶段开启时固定并记录来源，变动使用 Assignment 版本和审计；不能静默降低 all 的分母。

阶段决定记录在 approval_stage_decisions；最终 ApprovalDecision 仍属于原 approval_id。阶段已批准不等于整个请求批准，UI 和 Token 服务只能消费请求级最终结果。

any/all 的拒绝规则作用于请求/阶段终结前的有效决定；已经提交的唯一最终决定不能被迟到请求覆盖。并发批准/拒绝按锁/CAS 的有效提交次序与已冻结策略确定结果，不能在发出 Grant 后再用迟到拒绝静默改写历史。

## 4. 委托、转交与升级

委托记录委托人、受托人、适用组/流程/操作范围、有效期和原因，须当前授权有效。受托人获得最小且有期限的审批责任，不能继承委托人的全部系统权限。避免自批、循环委托及超范围处理。

升级由持久定时器触发，产生新的 Assignment revision 和审计，并停用旧分配；旧分配页面提交决定返回版本冲突。升级不能默认为批准，不能重置请求参数或无限延长 expires_at。

无可用审批人、委托失效、审批人离职或 all 集合不再可完成时进入明确等待/人工分配处理；期限到达默认 expired。授权管理员可以按制度调整分配，不能直接修改历史决定。

## 5. 决定提交与并发

决定事务验证：当前主体/组/委托 Scope、Assignment revision、未终结阶段/请求、有效期、参数 Hash 及回避规则。写入阶段决定/最终决定、CAS 更新状态及 Outbox 同事务，审计可靠留存。

同 decision_id 或 Idempotency-Key 相同内容重放返回原结果；不同内容冲突。并发批准/拒绝由锁/CAS 和策略计算确定唯一结果。旧 Assignment 或已终结请求不接受新的决定，不能覆盖第一次已经提交的事实。

每个阶段创建一个主体到决定的唯一约束，最终请求最多一条生效终结决定；所有拒绝、过期、取消和批准均记录原因、操作者/系统身份及时间。

## 6. 授权与动作执行

审批批准是执行必要条件之一，Tool Gateway 仍在实际调用前检查当前主体、Workflow Binding、工具风险、资源 ACL、环境及预算。

短时一次性 Approval Token 绑定 execution_scope、Owner/Step、action_id、Tool/参数 Hash/资源和有效期。首次消费通过 CAS 兑换该 Action 的持久 authorization_grant_ref；重复网络 Attempt 不重复消费原 Token，而是在同一 Action 下检查绑定、当前授权和 Grant 有效期。Grant 过期、请求撤回或 Policy 改变时停止执行并按策略重新审批。

一个 Token 不能授权新 action_id、新参数或补偿操作。恢复审批后无需重复产生新外部写入 Key，副作用协议见 [02](02-production-connectors-and-integration-governance.md)。

## 7. 拒绝、撤回与取消

| 时点 | 撤回/取消的含义 |
|---|---|
| 等待审批，动作未提交 | 终结请求为 cancelled，停用 Assignment，停止新动作 |
| 已批准但动作未提交 | 撤销未使用的 Grant，CAS 抢占动作提交状态；竞争失败按在途操作处理 |
| 外部动作已提交 | 标记取消请求并确认外部事实，不宣称已经撤销工单 |
| 外部已成功 | 如允许，另建补偿 Action 并获得所需授权/审批；不可补偿时按制度人工补救 |
| 外部状态 UNKNOWN | 进入对账/NEEDS_REVIEW，不能以撤回掩盖已发生效果 |

申请人可以按企业制度撤回自己的未提交动作；跨阶段、提交后的撤回条件须在 M0 业务规则中冻结。Critical 操作、付款、人事关键变更不因存在 Approval Center 就自动进入工单试点范围。

## 8. 审计、界面与验收

记录 policy version、请求、阶段、Assignment revision、委托/升级、决定、Hash、Grant、调用及外部响应引用。业务审计使用真实受控主体，Trace 默认匿名；详尽参数仅向具备当前资源权限的审批人显示。

验收覆盖：合法审批、组 any/all、多阶段、回避、委托范围/到期、升级竞态、双人并发决定、重放、参数变化、离职撤权、Grant 过期、撤回与在途竞争。旧 Agent 审批回调继续使用原 ID 和授权语义，直接 Workflow 审批没有伪造 Agent 数据。
