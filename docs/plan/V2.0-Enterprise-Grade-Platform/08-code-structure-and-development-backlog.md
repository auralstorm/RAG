# 08｜代码结构、任务 Backlog 与依赖

> 版本：V2.0。执行顺序和验收见 [09](09-complete-implementation-plan-and-acceptance.md)，契约见 [统一规则](../../architecture/统一契约与跨版本演进规则.md) 与 [07](07-database-api-and-contract-design.md)。

## 1. 模块与实现位置

增量扩展现有代码仓的 Identity/Policy、Model Gateway、Budget/Metering、Security/Lifecycle、Evaluation/Operations、Recovery/Journal。业务 RAG/Agent/Workflow、Approval/Action、Outbox 和审计事实源复用，不按 V2.0 新建平行平台。

```text
backend/app/modules/
  identity/             # reuse authentication / organization / Workspace / ACL
  model_gateway/        # route policies and resolutions
  budget/               # admission / reservation / atomic constraints
  metering/             # usage / ledger / reconciliation
  security/             # scoped incidents and controls
  lifecycle/            # holds / deletion plans / verification
  operations/           # SLO / capacity / control gates
  recovery/             # Recovery Set / run / evidence / journal adapter
  evaluation/           # reuse runners and add platform checks
workers/
  usage_reconciliation/
  lifecycle_verification/
  recovery_verification/
frontend/
  apps/
    chat/src/features/workspace/   # 当前协作范围与可用性提示
    admin/src/features/
      workspace/                  # 组织/成员与资源管理
      governance/
      operations/
  packages/
    ui/
    api-client/
    shared/
tests/
  resource_authorization/
  budget_and_routing/
  upgrade_and_recovery/
```

前端沿用 [ADR-0014](../../adr/0014-monorepo-and-independent-frontend-apps.md) 的两个独立应用及公共包，不另起运营前端项目。目录是职责建议，按现有仓库实际分层合并；版本/锁文件/云服务/CI 命令从真实配置查找，不在设计目录生成第二套业务源码。

## 2. 接口职责

| 模块 | 公共能力 | 内部负责 |
|---|---|---|
| Identity/Policy | resolve/authorize/verify | 复用当前主体、组织/成员与资源 ACL、旧入口适配 |
| RouteService | resolve(snapshot, constraints) | 授权候选、能力/区域/索引/预算和可比配置 |
| BudgetService | reserve/dispatch/settle/reconcile | 多级原子准入、未知预留、余额和并发 |
| MeteringService | record_usage/append_entry/reconcile | 来源/版本去重、Decimal、账单差异与调整 |
| Lifecycle/Security | contain/plan_delete/verify | 当前授权、最小化、保留和恢复后删除 |
| RecoveryService | capture/restore/verify/release | 集合/依赖、外部事实/费用、Epoch 和 Gate |

领域代码使用平台类型/接口；网络、数据库、供应商账单、Secret、对象存储和时钟置于 Adapter。恢复/计量不是直接改状态或任意记账入口，真实集成验证事务、独立持久证据和外部事实。

## 3. 任务与适用范围

P0 是单企业范围的交付与安全可靠性必需项；P1 条件增强按实际需求安排。共 52 条任务：47 条 P0、5 条 P1。Owner 为建议角色，M0 指定实际负责人/Reviewer。

### A — 范围、契约与基线（M0）

| ID | 任务 | 优先级 | 适用范围 | Owner | 验收 |
|---|---|---|---|---|---|
| A-01 | 单企业部署与数据要求冻结 | P0 | 全部 | Product/Security | 已确认产品范围，实际组织/部署/地域与数据要求具名 |
| A-02 | 实际上游/数据/消费者盘点 | P0 | 全部 | Backend | 旧 ID/Key/Owner/费用/在途引用有清单 |
| A-03 | SLO/容量/RPO/RTO/制度定义 | P0 | 全部 | Business/Platform | 指标分母/环境/目标/保留/恢复可验收 |
| A-04 | 授权/预算/恢复公共 Contract | P0 | 全部 | Architect | 字段/状态/失败/兼容与执行范围一致 |
| A-05 | 生成制品/迁移/CI 方案 | P0 | 全部 | Backend/QA | OpenAPI/Schema/Alembic 增量与消费者对应 |
| A-06 | 内部权限/高可用技术 POC | P0 | 全部 | Platform/QA | 真实故障域、资源 ACL/负向访问/连接池验证 |
| A-07 | 预留/用量/Journal/恢复 POC | P0 | 全部 | Backend/Integration | 未知提交/并发/账单/恢复证据可复现 |
| A-08 | ADR-0011/0012 与风险评审 | P0 | 全部 | Architect/Business | 依据 ADR-0013 范围，候选/证据/取舍/限制记录 |

### B — 企业内部成员与资源权限（M1）

| ID | 任务 | 优先级 | 适用范围 | Owner | 验收 |
|---|---|---|---|---|---|
| B-01 | 复用组织/Workspace 与资源权限 | P0 | 全部 | Backend | 盘点已有能力，补当前协作缺项，保留 UUID/ACL |
| B-02 | 可信主体/成员/旧入口适配 | P0 | 全部 | Security/Backend | 请求/消息不授予权限，缺必需授权信息拒绝 |
| B-03 | DB 查询与资源关系授权 | P0 | 全部 | Backend | 多用户/角色越权与未授权关系绑定失败，原 Unique 不变义 |
| B-04 | 索引/缓存/对象/队列/Secret 授权 | P0 | 全部 | Platform | 复用 Owner/ACL，撤权与派生数据访问一致 |
| B-05 | 企业组织/Workspace 与成员管理 | P0 | 全部 | Backend/Frontend | 管理权/内容权限分开，撤权保留在途/未知事实 |
| B-06 | 存量业务升级与授权回归 | P0 | 全部 | QA | 旧 Key/快照/ACL/额度/Grant/Timer/删除标记不变义 |

### C — 高可用与容量（M2）

| ID | 任务 | 优先级 | 适用范围 | Owner | 验收 |
|---|---|---|---|---|---|
| C-01 | API/健康路由/无进程状态 | P0 | 全部 | Backend/Platform | 重启/路由不丢请求/游标/当前授权 |
| C-02 | DB/MQ/存储故障域与切换 | P0 | 全部 | Platform | 写主/确认/副本/密钥依赖经过真实验证 |
| C-03 | Worker/Outbox/Timer 租约与 Epoch | P0 | 全部 | Backend | 旧执行者不能覆盖，原 Key 不重建 |
| C-04 | 隔离池/配额/排队与降级 | P0 | 全部 | Platform | 在线/评测/恢复负载隔离，不突破外部限制 |
| C-05 | 伸缩/排空/滚动发布 | P0 | 全部 | Platform | 缩容安全持久化，未知效果不盲重试 |
| C-06 | 容量/供应商故障与 SLO 验证 | P0 | 全部 | QA | 按冻结负载/SLO，分布/饱和/恢复可解释 |
| C-07 | Kubernetes/额外服务拆分评估 | P1 | 条件 | Architect | 真实收益/成本明确，不隐性改技术基线 |

### D — 路由、额度和费用（M3）

| ID | 任务 | 优先级 | 适用范围 | Owner | 验收 |
|---|---|---|---|---|---|
| D-01 | Route Policy/候选/版本快照 | P0 | 全部 | Backend | 能力/授权/地区/向量空间/评测约束保持 |
| D-02 | Profile/价格/单位/账单 Adapter | P0 | 全部 | Integration | 来源/版本/币种/不确定粒度明确 |
| D-03 | 多级预算原子预留/准入 | P0 | 全部 | Backend | 并发不超分配，拒绝未知严格上界 |
| D-04 | 派发/取消/未知预留 | P0 | 全部 | Backend | 失联/TTL 不自动退款，真实重试独立额度 |
| D-05 | Usage/Ledger 去重/Decimal/调整 | P0 | 全部 | Backend | 来源版本唯一，修正追加不覆盖/重复成本 |
| D-06 | 外部账单/缺失 usage 对账 | P0 | 全部 | Integration/QA | 未确认差异可追溯，按证据释放/结算 |
| D-07 | Run/Step/Workflow 兼容视图 | P0 | 全部 | Backend | 旧用量/预算与 Ledger 分工正确 |
| D-08 | 费用/恢复/Scope 并发集成测试 | P0 | 全部 | QA | 模型取消、路由失败、DB/Redis/恢复不漏账 |
| D-09 | 自动成本优化与更多候选 | P1 | 条件 | RAG/Business | 回归/质量/数据约束通过后启用 |

### E — 安全与数据运营（M4）

| ID | 任务 | 优先级 | 适用范围 | Owner | 验收 |
|---|---|---|---|---|---|
| E-01 | Scope/服务身份/跨范围管理 | P0 | 全部 | Security | 目的/时限/角色/资源一致，无全局空值放行 |
| E-02 | Secret/网络/轮换/恢复 | P0 | 全部 | Security/Platform | 当前最小权限、旧产物与密钥可恢复 |
| E-03 | Security Incident/遏制/审计 | P0 | 全部 | Security | 处置/恢复证据完整，不跳过授权 |
| E-04 | Hold/删除/员工撤权与恢复 tombstone | P0 | 全部 | Backend | 派生数据清理，未知业务/账目及必要留存闭合 |
| E-05 | 供应链/配置/镜像检查 | P0 | 全部 | Platform | 真实制品/版本/风险与回滚记录 |
| E-06 | 注入/隐私/IDOR/删除负向测试 | P0 | 全部 | QA/Security | 严重越权/泄露/残留阻断发布 |
| E-07 | 额外认证/制度报表 | P1 | 条件 | Business/Security | 正式范围/评估证据，不声明未取得认证 |

### F — 质量、SLO 与 Admin（M5）

| ID | 任务 | 优先级 | 适用范围 | Owner | 验收 |
|---|---|---|---|---|---|
| F-01 | 复用多目标 Evaluation/版本 Gate | P0 | 全部 | QA/Backend | 目标/配置/数据集可比，无平行评测系统 |
| F-02 | 企业资源权限/恢复 Adapter 与漂移 | P0 | 全部 | QA | 确定性证据、缺分失败，不自动改发布配置 |
| F-03 | SLI/SLO/错误预算/告警 | P0 | 全部 | Platform | 用户端到端与阶段指标真实分母 |
| F-04 | Trace/Metrics/Audit 关联 | P0 | 全部 | Platform | Scope/用量/Action/恢复可诊断，隐私/基数受控 |
| F-05 | Workspace/成本/安全/恢复 Admin | P0 | 全部 | Frontend | 实际授权与事实展示，未知/部分恢复不冒充成功 |
| F-06 | 角色/断线/管理动作联调 | P0 | 全部 | Frontend/QA | 当前授权、异常、并发和证据一致 |
| F-07 | 复杂运营报表/优化工作台 | P1 | 条件 | Frontend | 复用已验证指标与数据边界 |

### G — 灾备、升级与生产（M6–M8）

| ID | 任务 | 优先级 | 适用范围 | Owner | 验收 |
|---|---|---|---|---|---|
| G-01 | Recovery Set/Manifest/依赖 | P0 | 全部 | Platform | DB/对象/密钥/配置/归属/账本/证据可验证 |
| G-02 | Journal 与提交前凭证 | P0 | 全部 | Backend/Platform | 原 Key/Attempt/Hash 保持，缺凭证不发副作用 |
| G-03 | Recovery Run/Epoch/Gate | P0 | 全部 | Backend | 读/写/计费准入分开，旧执行者隔离 |
| G-04 | 外部效果/费用/待办恢复 | P0 | 全部 | Integration/QA | PITR 丢本地记录仍不重复工单/漏账 |
| G-05 | 跨版本迁移/灰度/回滚 | P0 | 全部 | Backend/QA | 旧契约/状态/Key/价格/审批/删除不变义 |
| G-06 | 真实 RPO/RTO/故障演练 | P0 | 全部 | QA/Platform | 实际依赖/范围/目标、UNKNOWN/停用处理闭合 |
| G-07 | 生产试点/SLO/Runbook/签署 | P0 | 全部 | Business/Platform | 单企业指标、业务工单与安全/运维通过 |
| G-08 | 跨地域多活/更高灾备档位 | P1 | 条件 | Architect/Platform | 数据/成本/依赖/一致性需求批准后验证 |

## 4. 交付与验证

任务有真实 Owner/Reviewer、契约、实现/PR、验证命令和证据；实际目标与 P1 条件在 M0 固定，未启用项记录范围而不伪造完成。实现检查按 AGENTS.md 和实际代码仓执行，文档变更检查引用/示例/任务覆盖，不补造运行结果。

依赖链：A → B 企业资源授权 → C/D/E 可靠运营 → F 质量/UI → G 恢复/升级 → 生产试点。成本/恢复/安全与 UI 可按固定 Contract 并行；生产放行依准入和真实验收，不用模块数量或代码行数判定完成。
