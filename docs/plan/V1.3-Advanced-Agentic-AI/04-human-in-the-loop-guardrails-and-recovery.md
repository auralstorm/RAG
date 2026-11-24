# V1.3-04 Human-in-the-loop、Guardrails 与失败恢复

> 公共字段、状态、事件、权限与迁移映射见 [统一契约与跨版本演进规则](../../architecture/统一契约与跨版本演进规则.md)；本文件描述本版能力及增量，具体实现须通过契约与升级验收。

## 1. 目标与边界

V1.3 引入 Agent 执行过程中的人工介入能力，用于补充信息、确认高风险步骤、处理冲突和恢复异常。它不是 V1.4 企业审批 Workflow 的替代品。

## 2. 人工介入类型

1. Clarification：用户补充缺失条件。
2. Approval：对受控动作进行明确确认。
3. Review：人工检查 Agent 生成的结果或证据。
4. Exception Handling：处理不可自动恢复的异常。
5. Resume Decision：决定继续、调整计划或终止。

每种交互需定义请求者、目标角色、上下文摘要、待决事项、允许操作、截止时间和超时策略。

## 3. 风险分级

| 风险级别 | 示例 | 默认处理 |
|---|---|---|
| Low | 只读检索、摘要 | 可自动执行 |
| Medium | 多系统只读查询、生成草稿 | 自动执行并增强记录 |
| High | 发送消息、修改业务记录、触发外部动作 | 明确审批后才执行 |
| Critical | 权限变更、资金/人事关键操作、不可逆动作 | V1.3 默认禁止或仅 Mock |

风险等级由平台 Policy 决策，不能由 Agent 自己声明降级。Tool Registry 必须声明副作用等级、幂等能力和审批要求。

## 4. Approval Contract

沿用 V1.1 最小协议，并按统一契约第 5 节扩展人工交互：

- ApprovalRequest：approval_id、run_id/step_id、requested_action、target_resource、parameter_hash、input_summary、risk_level、policy_decision_ref、approver_role、expires_at、idempotency_key、status（初始 pending）。
- ApprovalDecision：decision_id、approval_id、decision（approved/rejected/expired/cancelled）、decision_reason、decided_by/decided_at、parameter_hash。

human_interactions.id 作为审批请求 ID（仅 approval 类型）；决定与业务动作执行结果分别记录。旧 /approval-result 通过 Adapter 转到同一决定服务，验证身份、角色、Hash、有效期与重放，不另建一套审批事实。V1.4 Approval Center 可增加分配/升级/撤回流程实体，继续引用相同审批 ID。

审批必须绑定具体动作参数摘要。参数发生变化必须重新审批，不能复用旧审批结果。

## 5. 防止审批绕过

- Agent 不能自行生成 Approved 状态。
- Tool Gateway 在真正执行前校验 Approval Token。
- Approval Token 短时有效、单次使用，并绑定 Run、Step、Tool、参数 Hash 和资源。
- 参数、目标资源或权限上下文变化时审批失效。
- 超时默认拒绝，不默认批准。
- 审批人不能批准自己发起的高风险操作（按组织策略配置）。
- 所有审批决定写入不可篡改审计事件。

## 6. Guardrails 分层

### 输入层
- 身份认证、请求限流、输入长度限制。
- Prompt Injection / 越权意图检测。
- 敏感信息识别和必要脱敏。

### 规划层
- Plan Schema 校验。
- Tool / Agent allowlist。
- 任务 DAG 无环校验。
- 风险与预算校验。
- 禁止 Planner 生成未授权能力。

### 执行层
- Tool Gateway Policy Enforcement。
- 参数 Schema 校验。
- 资源级 ACL。
- 幂等键、超时、限流。
- 高风险动作审批门禁。

### 输出层
- Evidence / Citation 验证。
- 敏感信息检查。
- 输出格式与业务规则检查。
- 不确定性和失败状态显式表达。

## 7. Prompt Injection 防御

威胁来源包括用户输入、知识库文档、网页、Connector 返回值、工具错误消息和 Worker 输出。所有外部内容均视为不可信数据。

防护原则：
- 系统指令与数据内容严格分层。
- 工具输出不能覆盖 System Policy。
- 工具参数由 Schema 和 Policy 双重校验。
- 禁止模型输出直接拼接执行 Shell / SQL 等危险命令。
- SQL Connector 使用只读账号、参数化查询和表/列 allowlist。
- 高风险动作不允许仅凭模型判断通过。
- 对注入检测结果进行记录和评测。

## 8. 失败恢复矩阵

| 故障 | 自动处理 | 人工处理 |
|---|---|---|
| Model 429 / transient 5xx | 有界退避重试 | 超限后提示 |
| Tool timeout | 幂等安全时重试 | 不确定提交状态时核对 |
| Policy deny | 不重试、不换权限 | 由有权管理员处理策略 |
| Invalid Plan | 有界修复重试 | 持续失败后提示 |
| Worker failure | 按 Plan 降级或重派 | 关键任务失败时介入 |
| Evidence conflict | 追加检索/验证 | 无法解决时人工复核 |
| Checkpoint write failure | 停止危险步骤 | 运维介入 |
| Approval expired | 取消待执行动作 | 重新发起审批 |

## 9. 取消、暂停与恢复

- 暂停只在安全边界生效，不保证中断正在执行的不可取消外部请求。
- Resume 前重新校验用户身份、Agent 发布版本、工具授权和资源 ACL。
- 若 Agent Version 已撤销或 Tool 权限已变化，不得按旧权限恢复。
- 取消后不可继续执行未完成任务；恢复应显式创建新的执行尝试。
- 恢复过程需校验 Checkpoint 完整性与 Schema 版本。

## 10. 审计事件

至少记录：
- Plan created / revised / rejected
- Task / Step started / completed / failed
- Tool invocation / policy decision
- Agent handoff
- Approval requested / approved / rejected / expired
- Checkpoint created / restored
- Run paused / resumed / cancelled / timed out
- Guardrail triggered
- Budget exhausted

审计记录应包含主体、Agent Version、Run、Trace、对象、结果、时间、策略引用和必要的前后摘要；避免记录密钥和不必要的敏感正文。

## 11. 验收标准

- 高风险 Tool 未审批不能执行。
- 审批参数变化后旧审批失效。
- 超时审批默认拒绝。
- 权限拒绝不会触发自动换工具绕过。
- 取消、暂停、恢复状态一致且可追踪。
- Prompt Injection 测试集能验证关键防护。
- 故障矩阵中的重试策略可通过自动化测试验证。
