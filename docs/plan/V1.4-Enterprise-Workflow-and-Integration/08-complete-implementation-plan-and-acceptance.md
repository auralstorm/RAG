# 08｜完整研发实施计划与阶段验收

> 版本：V1.4。里程碑优先于日历；任务 ID 见 [07](07-code-structure-and-development-backlog.md)，契约见 [统一规则](../../architecture/统一契约与跨版本演进规则.md) 与 [06](06-database-api-and-contract-design.md)。实际周期/容量由 M0 团队与 POC 估算确认。

## 1. Entry Criteria

需要确认现有 Identity/Policy、Tool Gateway/Connector、不可变 Agent Version、HITL 最小请求/决定、Audit/Trace、Outbox、Evaluation、数据库/消息/对象存储可以复用；上游关键数据和契约有真实验收记录。

基础 Workflow 不强制启用 Multi-Agent；已批准的上游范围裁剪不免除对实际复用能力的验证。若缺基础模块，先安排具名依赖补齐任务，不能在 V1.4 复制一套以跳过上游。

## 2. M0 冻结清单

| 决策/资料 | 当前状态 | 必须形成的交付 |
|---|---|---|
| 部署模式 | 用户已确认单企业内部部署 | 沿用 ADR-0013，部署 namespace 与现有主体/组织/资源 ACL |
| 首个流程 | 用户已确认工单创建→审批→结果确认 | 申请/审批/外部写入/确认的真实业务验收脚本 |
| 工单系统及接口 | 待提供/调查 | 厂商/部署、认证、Schema、错误、幂等/唯一键、回查/一致性、取消限制 |
| 审批制度 | 待业务冻结 | 组/阶段/any/all、回避、委托/升级、时限、撤回与在途处理 |
| Workflow 可靠底座 | ADR-0009 proposed | DB/Outbox/Timer/租约、长等待和外部响应丢失 POC |
| 权限与生命周期 | 沿用基线，细节待制度确认 | 当前主体/服务身份、业务 ACL、Secret、保留/删除、补救操作权限 |
| 质量/性能/恢复目标 | 尚无实测值 | 测试环境、并发/积压/长等待假设、业务指标和阈值 |

资料未齐时可以完成通用 Schema/Mock 与受控技术验证；相关真实 Connector、制度或生产启用 Gate 保持未通过，不补造批准或系统能力。

## 3. 里程碑

### M0：场景、契约与 POC

任务：A-01–A-07。交付输入/流程/状态 Schema、API/Event 初版、存量迁移方案、工单/审批能力矩阵、Fake 与真实 Sandbox POC 计划/记录及 ADR 评审。

Exit：各 P0 Owner/Reviewer、依赖、验收明确；核心执行域和幂等/未知提交规则无未决歧义；真实接口/制度缺项有负责人和计划。开始具体生产 Adapter 前，其认证/Schema/副作用能力必须冻结。

### M1：可靠 Workflow 核心

任务：B-01–B-04、E-01–E-03。交付不可变版本、实例/步骤/Attempt、条件/等待基础、DB 租约/Timer/Outbox 及逻辑 Action 记录。

Exit：非法 DAG/条件/未知字段拒绝；并发创建和 published 重试同实例；Worker 重启、消息重复、长 Timer 和旧 fencing 不能丢状态或重复推进；等待不占 Worker。

### M2：Connector 与只读/Sandbox

任务：C-01–C-04/C-06 的非生产部分。交付试点 Adapter、Tool/配置快照、Secret/网络/健康、读取/查询及目标系统幂等/确认 POC。

Exit：接口能力有真实证据，凭据/SSRF/最小权限检查通过；Mock/只读与生产准入分别记录；确认/取消限制明确。没有可靠外部防重复的创建操作保持自动写入关闭。

### M3：Approval Center

任务：D-01–D-09，复用 M1 Timer 支持到期/升级。交付原请求 ID 兼容、Policy/Stage/Assignment、any/all/串行阶段、委托、升级、重放/CAS、撤回、绑定 Token/Grant 和审计。

Exit：当前 Assignment/主体/Hash/有效期验证通过，阶段通过不冒充最终批准，旧回调保持 Agent 语义；升级与批准/拒绝并发结果唯一，撤回不能掩盖在途效果。

### M4：工单业务动作、确认与补偿

任务：B-05–B-07、C-05/E-04/E-05/E-08，B-06 从 Fake 到受控真实试点分阶段验证。交付“申请/草稿→审批→创建→确认”、UNKNOWN 对账、独立补偿和受控 Agent 启动。

Exit：所有写入绑定当前 Policy、Action/参数、审批/Grant/Key/外部引用；批准前无外部创建；丢失响应不重复建单；确认失败不回到创建；补偿有独立授权，失败/不可逆效果清晰记录。

### M5：Webhook、Schedule 与恢复调度

任务：E-06–E-08。交付来源/签名/Schema、稳定源事件去重、受控关联、Schedule 版本/UTC occurrence、missed/DST 规则、停用及恢复扫描。

Exit：伪造/重放/错资源不能推进；同 source_key 重复受理同结果；扫描/领导者变化不重复发生；到期唤醒重校验状态/授权，审批升级不自动批准。

### M6：Chat/Admin、评测和全链路联调

任务：F-01–F-05、G-01–G-05。交付工单申请/进度/结果、审批中心、Workflow/Policy/Connector 管理、对账补偿 UI、Timeline、质量 Gate 和审计/告警。

Exit：UI/API 权限一致，SSE 重连/重复与后台事实一致；无法确认的外部效果明确显示；Workflow 评测绑定实例和版本，旧 Agent/审批/Tool/评测升级回归通过。

### M7：真实试点、运维与发布

任务：C-06 生产准入及 G-06–G-08，G-07 真实工单试点及业务签署。交付实际环境压测/故障/恢复、备份、配置/凭据/应用回滚 Runbook、试点限定用户/流程、UAT、生产观测与风险记录。

Exit：至少一个真实业务流程满足路线图 §5.5，制度、审批、幂等、外部结果及业务审计有证据；P0、安全/副作用阻断项关闭，业务/平台/安全/QA/运维签署。只有 Mock 通过不能签生产 Go。

## 4. 必测矩阵

| 领域 | 场景 | 通过条件 |
|---|---|---|
| 定义/版本 | 非法引用、环图、发布后修改、版本切换 | 服务端拒绝非法数据，历史实例固定快照 |
| 实例幂等 | 并发提交、同 Key 改内容、published 指针改变 | 一次申请一个实例，冲突可解释 |
| 身份/权限 | IDOR、服务账号、撤权/离职、Workflow Scope 伪造 | 每次边界当前授权；无越权或权限扩大 |
| 审批 | any/all/串行、回避、委托失效、升级竞态、重放 | 唯一有效最终决定，参数/角色/有效期绑定 |
| 写入 | 批准前调用、Grant 重放/到期、响应丢失 | 无未批写入，无重复效果，未知提交转对账 |
| 确认 | 外部成功但本地失败、暂未查询到、只读暂时失败 | 原 Key/已成功事实保持，不重走 create |
| 补偿/取消 | 执行中取消、不可逆工单、补偿拒绝/超时 | 独立授权，未知事实不隐藏，原/补偿均审计 |
| 可靠性 | Worker Crash、Outbox 失败、MQ 重复、旧租约迟到 | 状态可恢复且推进有幂等/租约保护 |
| 触发/Timer | 篡改、重复源事件、重启、DST、missed occurrence | 唤醒按持久 Owner/UTC/版本/权限校验 |
| 兼容 | 旧 Run/Tool/审批/API/Eval、数据回填 | 原 ID/契约/数据语义不被破坏 |
| UX/隐私 | 暂态、断线、错角色、Trace/附件/Secret、删除 | UI 事实一致，无未授权暴露及无限留存 |

规则与故障测试先用 Fake Clock/Connector，事务/锁/队列用真实基础设施集成，再对正式接口/试点验证外部事实。质量报告不以模型评分代替权限、审批和副作用确定性证据。

## 5. 指标与证据

记录 Workflow 成功率/正确完成率、等待及升级时长、无批准写入数、重复外部创建数、UNKNOWN 数量/时长、对账成功率、补偿结果、恢复延迟、Timer 延迟、Outbox/队列积压、Connector 错误/用量。

安全必过项：成功越权/未批准写入/凭据暴露为零，重复副作用失败样本必须关闭。其他阈值按业务风险、数据集、环境和容量确认；报告固定 Definition/Tool/Policy/Profile/Fixture 版本，不补造 SLA 或“行业通用成功率”。

## 6. 发布与运维

先部署兼容 Migration/API/Worker/Schema → 权限/旧版本回归 → 验证 Mock/Sandbox 与生产能力证据 → 发布 Workflow/审批策略 → 限制工单试点 → 监控真实效果与积压 → UAT/Go 签署。

停用写能力或回滚应用时，保留在途 Action/审批/Timer/实例事实，由恢复/对账 Runbook 处理；旧 Workflow 指针回滚只影响新实例。禁止用破坏性 downgrade 清空待确认效果。

Runbook 至少包含：Connector 凭据轮换/失效、UNKNOWN 对账、不可补偿工单、取消竞争、审批人缺席/委托/升级、Outbox/Timer/Worker 恢复、当前授权撤销、业务数据删除及应用/配置回滚。

## 7. 最终 DoD

- 工单申请到真实外部结果的端到端链路符合业务制度；Mock/真实环境证据分别记录。
- Workflow 与 Agent Run 独立，Tool/Policy/Approval/Evaluation 复用且兼容。
- 版本、审批、操作 Key、Attempt、外部响应和补偿事实可重建。
- 长等待/触发/取消/故障恢复、数据迁移、权限/隐私与性能验证通过。
- 核心 API/Event/Schema/Migration/Runbook 与实际代码一致，剩余风险有 Owner 和期限；真实系统/制度未冻结的能力不宣称已上线。
