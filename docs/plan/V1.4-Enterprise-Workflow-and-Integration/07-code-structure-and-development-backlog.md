# 07｜代码结构、模块职责与开发 Backlog

> 版本：V1.4。实施入口见 [08](08-complete-implementation-plan-and-acceptance.md)，接口/数据增量见 [06](06-database-api-and-contract-design.md)，公共解释源为 [统一契约](../../architecture/统一契约与跨版本演进规则.md)。

## 1. 实现边界

在现有代码仓增加 Workflow/Business Action/Approval 分配等领域能力。复用已有 Identity、Policy、Tool/Connector、Audit、Outbox、Trace、Object Storage、Evaluation，不按设计版本另起独立项目或复制第三方 SDK 封装。

示例目录表达职责，实际位置在 M0 与现有仓库合并；本设计文档目录不是业务代码目录。

```text
backend/app/
  modules/
    workflow/
      domain/           # Definition / Version / Instance / Step
      application/      # start / control / publish
      ports/            # approval / action / timer / event / repository
      infrastructure/   # persistence adapters
      api/
    business_action/
    approval/           # 扩展原请求/决定服务，新增 Stage / Assignment
    connector/          # 复用受控 Adapter，增加生产准入
    triggers/
  workers/
    workflow_worker.py
    durable_timer_worker.py
    outbox_dispatcher.py # 复用既有实现
    reconciliation_worker.py
frontend/
  apps/
    chat/src/features/
      workflow/         # 员工申请/进度/确认
      approvals/        # 授权审批人的待办处理
    admin/src/features/
      workflow/         # 流程定义与运营
      approvals/        # 审批策略及治理
      connectors/
  packages/
    ui/
    api-client/
    shared/
tests/
  contract/
  integration/
  workflow_scenarios/
  security/
  recovery/
```

Chat/Admin 两个独立应用及 pnpm 公共包沿用 [ADR-0014](../../adr/0014-monorepo-and-independent-frontend-apps.md)。配置、锁文件、构建命令和框架版本从实际仓库读取；代码仓生成 OpenAPI/JSON Schema/Migration 并维护 CI。本包不虚构已经存在的脚本或执行结果。

## 2. 深层模块接口

| 模块 | 对外能力 | 内部承担的复杂度 |
|---|---|---|
| Workflow Service | start/query/pause/resume/cancel | 实例/版本绑定、状态迁移、依赖与授权 |
| Scheduler/Timer | claim_due/schedule/wake | DB 租约、单调 fencing、到期与重复唤醒 |
| Business Action | prepare/submit/reconcile/compensate | 参数绑定、逻辑 Key、外部事实与补偿链 |
| Approval Service | request/decide/reassign/delegate/claim_grant | 组/阶段/委托/升级、并发、最终决定与 Grant |
| Connector/Gateway | execute/health/promote/disable | 受控协议、凭据、Policy、能力与生产准入 |
| Evaluation Adapter | run_workflow_case/collect_metrics | 复用 Profile/Runner/Gate，Workflow 目标路由 |

模块按平台类型传递引用；UI/API 不直接操作状态表，Workflow 不直接发外部请求，Approval 不把决定视为外部执行成功。领域测试使用 Fake Clock/Gateway/Repository 等边界，集成测试覆盖真实事务/租约与消息。

## 3. 优先级与任务

P0：本版范围或生产安全/可靠性退出条件必需；P1：增强项，延期记录依赖与风险。表中 Owner 是建议责任角色，M0 指定实际负责人和 Reviewer，不以角色名冒充已经分派。

### A — 范围、契约与迁移（M0）

| ID | 任务 | 优先级 | Owner | 验收 |
|---|---|---|---|---|
| A-01 | 工单接口/审批/补偿需求冻结 | P0 | Product/Integration | 真实系统、业务规则与待决项有依据和负责人 |
| A-02 | Workflow Definition Schema/状态 | P0 | Backend/Architect | 发布正反例、DAG/分支/Deadline 校验定义 |
| A-03 | Tool/Approval 执行域兼容 | P0 | Backend | Agent/Workflow Owner 检查及旧回调映射明确 |
| A-04 | OpenAPI/Event Schema 设计制品 | P0 | Backend/QA | 路径/字段/事件规范唯一，消费者兼容计划 |
| A-05 | 存量 DDL 与新增实体迁移 | P0 | Backend | 上游表盘点，Expand/回填/约束/回滚验证方案 |
| A-06 | 可靠调度与外部幂等 POC | P0 | Platform/Integration | 长等待/进程崩溃/响应丢失可复现并审查 ADR-0009 |
| A-07 | 单企业权限/保留/容量基线 | P0 | Security/QA | 实例 ACL、Secret、保留与负载假设确认 |

### B — Workflow 核心（M1/M4）

| ID | 任务 | 优先级 | Owner | 验收 |
|---|---|---|---|---|
| B-01 | Definition/Version Registry | P0 | Backend | 草稿、校验、不可变发布、回滚指针 |
| B-02 | Instance 创建/幂等 | P0 | Backend | 重复请求同实例，published 重试固定快照 |
| B-03 | Step/Attempt 与确定性解释器 | P0 | Backend | 条件/依赖/失败分支一致，旧 Attempt 不覆盖 |
| B-04 | DB Scheduler/租约/fencing | P0 | Platform | 并发领取、旧 Worker 迟到、恢复推进安全 |
| B-05 | pause/resume/cancel 控制 | P0 | Backend | 安全边界和 UNKNOWN/在途处理，不误报取消 |
| B-06 | 工单申请→审批→写入→确认 | P0 | Backend/Integration | Fake 与真实试点分别有 E2E 证据 |
| B-07 | 受控 start_workflow Agent Adapter | P0 | Backend | 来源 Run 关联，权限与状态独立，无伪造 Owner |
| B-08 | Workflow 调用独立 Agent Step | P1 | Backend | 经 Runtime Facade，输出不能批准业务动作 |

### C — 生产 Connector（M2/M4）

| ID | 任务 | 优先级 | Owner | 验收 |
|---|---|---|---|---|
| C-01 | 复用 Connector/Tool 注册与版本 | P0 | Integration | 无平行 Registry，配置/Binding 来源可追溯 |
| C-02 | 工单 REST/实际协议 Adapter | P0 | Integration | 真实 Sandbox Schema/错误/业务成功判定通过 |
| C-03 | Secret/网络/健康/轮换治理 | P0 | Security/Platform | 最小 Scope、TLS/SSRF/脱敏与停用在途处理 |
| C-04 | 外部幂等/唯一键/回查验收 | P0 | Integration/QA | 丢响应重放不重复工单；弱一致回查路径明确 |
| C-05 | Gateway Workflow Scope 与 commit_state | P0 | Backend | 旧 Agent DTO 兼容，UNKNOWN 不自动重试 |
| C-06 | 生产准入记录与启停 | P0 | Platform/Business | 连接健康不能自动启用写；试点范围有依据 |
| C-07 | 更多 HR/CRM/SQL/MCP 实例 | P1 | Integration | 逐系统独立权限/副作用验收，不继承工单结论 |

### D — Approval Center（M3）

| ID | 任务 | 优先级 | Owner | 验收 |
|---|---|---|---|---|
| D-01 | 复用请求/决定及执行域迁移 | P0 | Backend | 旧 approval_id/回调继续有效，Workflow 无伪造 Run |
| D-02 | Policy Version/Stage/候选快照 | P0 | Backend | 单人、any/all、串行阶段可确定性验证 |
| D-03 | Assignment/决定 CAS 与重放 | P0 | Backend/QA | 同 ID 幂等，冲突内容/并发决定不覆盖 |
| D-04 | 委托 Scope/有效期/回避 | P0 | Security/Backend | 无自批/循环/权限扩大，撤销后不可继续决定 |
| D-05 | 到期/升级 Timer 与分配 revision | P0 | Backend | 旧待办失效，不自动批准/无限延长 |
| D-06 | 参数/Binding Hash 与最终批准 | P0 | Backend | 阶段通过不冒充最终批准，变更重新审批 |
| D-07 | 一次性 Token/持久 Grant | P0 | Backend/Security | 绑定 Action，重放不再授权，过期/撤回/当前 Policy 校验 |
| D-08 | 撤回/取消与在途动作竞争 | P0 | Backend/QA | 动作未提交可阻止，在途必须确认和补救 |
| D-09 | 决定/分配/委托审计 | P0 | Backend | 真正主体、策略、理由、来源与 Hash 可追溯 |

### E — 持久触发、对账与补偿（M1/M4/M5）

| ID | 任务 | 优先级 | Owner | 验收 |
|---|---|---|---|---|
| E-01 | 复用 Outbox/幂等消费者 | P0 | Platform | DB 成功/MQ 失败可修复，无重复推进 |
| E-02 | Timer 持久化/扫描/到期 | P0 | Platform | 跨天等待不占 Worker，恢复不重复触发 |
| E-03 | Business Action 逻辑效果账本 | P0 | Backend | 原操作 Key 与 Attempt/Tool Call 关联，事实不丢 |
| E-04 | UNKNOWN 对账与人工入口 | P0 | Integration/Backend | 未找到不等于无效果，无证据不能标成功 |
| E-05 | 独立补偿 Action/授权 | P0 | Backend | 原效果与补偿分开，重复补偿幂等，失败可人工处理 |
| E-06 | Webhook 来源/Schema/关联/去重 | P0 | Backend/Security | 重放/篡改/错资源不推进实例 |
| E-07 | Schedule 版本/UTC 发生去重 | P0 | Platform | 停用/重启/missed occurrence/时区案例符合规则 |
| E-08 | 完整恢复与取消状态闭合 | P0 | QA/Backend | UNKNOWN/补偿失败不隐藏到成功终态 |

### F — Chat/Admin（M6，可按冻结 API 并行）

| ID | 任务 | 优先级 | Owner | 验收 |
|---|---|---|---|---|
| F-01 | 工单草稿/申请/外部结果页面 | P0 | Frontend | 受理、审批、写入、确认状态有明确区别 |
| F-02 | Instance Timeline/SSE 控制 | P0 | Frontend | 重连/重复事件/暂停取消及权限状态一致 |
| F-03 | 审批待办/阶段/委托/升级 | P0 | Frontend | 当前分配与 Hash 展示，过期/转交不能提交旧决定 |
| F-04 | Workflow/Policy/Connector Admin | P0 | Frontend | 受控草稿与发布，生产准入和健康分别展示 |
| F-05 | 对账/补偿受控处理 | P0 | Frontend | 权限/证据/副作用说明，没有任意改状态入口 |
| F-06 | 任意图形 Designer/复杂报表 | P1 | Frontend | 在核心闭环完成后评估，不扩大 P0 |

### G — 质量、运维与发布（M6/M7）

| ID | 任务 | 优先级 | Owner | 验收 |
|---|---|---|---|---|
| G-01 | Workflow Evaluation Adapter/Gate | P0 | QA/Backend | 复用 Dataset/Profile，目标版本和指标可追溯 |
| G-02 | 迁移与旧 Agent/审批/Tool 回归 | P0 | QA/Backend | 升级保留 ID/Hash/TTL/权限，不复制平行事实 |
| G-03 | 权限/注入/Secret/IDOR 测试 | P0 | Security/QA | 严重越权和泄露失败阻断发布 |
| G-04 | 进程/队列/网络故障演练 | P0 | QA/Platform | 无重复外部效果，UNKNOWN 和补偿可解释 |
| G-05 | Trace/Metrics/Audit/告警 | P0 | Platform | 实例到外部动作/审批关联，默认匿名与独立留存 |
| G-06 | 压测/容量/长等待/备份恢复 | P0 | QA/Platform | 按冻结环境、时区/延迟/积压门槛报告 |
| G-07 | 真实工单试点/UAT/Runbook | P0 | Business/Platform | 真实业务负责人确认制度、结果、回滚及补救 |
| G-08 | 发布观察与风险闭合 | P0 | Product/QA | P0/关键安全/副作用问题关闭，剩余风险具名 |

## 4. 依赖与完成标准

A 契约/POC → B/E 可靠核心 → C 只读/Sandbox 与 D 审批 → B/C/E 写入确认/对账/补偿 → E 触发与定时 → F/G 联调/真实试点。UI 可基于冻结 OpenAPI/Fixture 并行，但生产操作依赖上游验收。

每个 Task 关联规范文件、Owner、Reviewer、真实 PR/实现、命令/测试证据和验收结果。Domain/API/Schema/迁移/前端变化按 AGENTS.md 的相关验证要求执行；涉及外部效果必须覆盖未知提交、重复请求和当前授权。任务 Done 与生产准入分别记录，不以 Mock 完成替代真实流程验收。
