# 05 — V1.2 代码结构、模块边界与开发 Backlog

> 公共字段、状态、事件、权限与迁移映射见 [统一契约与跨版本演进规则](../../architecture/统一契约与跨版本演进规则.md)；本文件描述本版能力及增量，具体实现须通过契约与升级验收。

## 1. 实施原则

沿用 V1.0/V1.1 模块化单体基线。V1.2 不因新增 Agent Builder、Evaluation、Release 功能就全面拆微服务。通过清晰领域模块、应用服务、Repository、事件和 Adapter 保持边界；只有评测 Worker 等异步负载可独立部署。

## 2. 推荐仓库结构

```text
enterprise-agentic-platform/
├── apps/
│   ├── api/                         # FastAPI 应用入口
│   └── worker/                      # Celery Worker
├── backend/
│   ├── core/
│   │   ├── auth/
│   │   ├── rbac/
│   │   ├── policy/
│   │   ├── audit/
│   │   ├── events/
│   │   ├── observability/
│   │   └── errors/
│   ├── modules/
│   │   ├── agent_registry/
│   │   │   ├── domain/
│   │   │   ├── application/
│   │   │   ├── infrastructure/
│   │   │   └── api/
│   │   ├── agent_definition/
│   │   ├── prompt_management/
│   │   ├── agent_playground/
│   │   ├── agent_evaluation/
│   │   ├── agent_release/
│   │   ├── agent_access/
│   │   ├── agent_runtime/            # 调用 V1.1 Runtime Facade
│   │   ├── tool_gateway/             # 调用 V1.1 Gateway
│   │   ├── rag_engine/               # 调用 V1.0 Retriever Contract
│   │   └── model_gateway/
│   ├── adapters/
│   │   ├── langgraph/
│   │   ├── evaluation_scorers/
│   │   └── object_storage/
│   └── migrations/
├── frontend/
│   ├── apps/
│   │   ├── chat/src/features/agents/  # 员工使用已发布 Agent
│   │   └── admin/src/
│   │       ├── app/
│   │       ├── routes/
│   │       └── features/
│   │           ├── agents/
│   │           ├── agent-editor/
│   │           ├── prompts/
│   │           ├── playground/
│   │           ├── evaluation/
│   │           └── releases/
│   └── packages/
│       ├── ui/
│       ├── api-client/
│       └── shared/
├── contracts/
│   ├── agent-definition/
│   ├── prompt/
│   ├── evaluation/
│   └── events/
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── contract/
│   ├── security/
│   ├── evaluation/
│   └── e2e/
├── deploy/
└── docs/
```

前端增量沿用 [ADR-0014](../../adr/0014-monorepo-and-independent-frontend-apps.md) 和 V1.0 pnpm workspace 基线：Chat/Admin 分别构建/部署，公共包改动覆盖消费者，不增加第三个 Web 应用。

## 3. 模块职责

### agent_registry
Agent 稳定身份、元数据、Owner、团队、可见性和生命周期。

### agent_definition
Definition Schema、默认值、校验、迁移、资源引用解析和快照生成。

### prompt_management
Prompt Template、Prompt Version、变量 Schema、Render、Diff 和权限。

### agent_playground
测试会话、Sandbox Context、Run 发起、SSE 事件和调试数据聚合。不得自行实现 Agent Runtime。

### agent_evaluation
Dataset、Profile、Job、Runner、Scorer、Result、Report、Compare 和 Gate。

### agent_release
发布校验编排、原子切换、回滚、暂停、发布记录和审批挂接点。

### agent_access
Agent 资源级授权和与既有 RBAC / Policy Engine 的适配。

## 4. 依赖方向

```text
API / UI
   |
Application Services
   |
Domain Modules
   |
Ports / Contracts
   |
Infrastructure Adapters
```

禁止：
- 前端直接访问数据库或内部 Worker。
- Agent Registry 直接调用 LangGraph 内部 API。
- Evaluation 模块绕过 Agent Runtime 自己执行 Tool。
- Agent Definition 直接持有供应商 Key。
- Agent Runtime 直接访问 Elasticsearch 或企业系统。
- 模块间循环依赖。
- 业务模块自行写入无统一 Schema 的审计日志。

## 5. Backlog 结构与优先级

优先级定义：
- P0：V1.2 发布阻断项。
- P1：V1.2 重要能力，若延期必须有明确风险接受。
- P2：增强项，可进入后续迭代。

### EPIC A — Agent Registry 与 Definition

| ID | 任务 | 优先级 | 验收 |
|---|---|---:|---|
| A-01 | Agent / Version 领域模型 | P0 | 生命周期与版本关系测试通过 |
| A-02 | Definition JSON Schema | P0 | 正反例和边界测试通过 |
| A-03 | Definition Validator | P0 | 资源存在性、权限、数值范围验证 |
| A-04 | Definition Migration Framework | P0 | 旧 Schema 可显式迁移 |
| A-05 | Agent CRUD API | P0 | 权限、分页、幂等测试通过 |
| A-06 | Version Draft API | P0 | 仅 Draft 可编辑 |
| A-07 | Snapshot Builder | P0 | 生成不可变完整快照 |
| A-08 | Agent Copy / Archive | P1 | 复制不复制秘密；归档检查引用 |

### EPIC B — Prompt Management

| ID | 任务 | 优先级 | 验收 |
|---|---|---:|---|
| B-01 | Prompt / Prompt Version 模型 | P0 | 版本不可变 |
| B-02 | Template Variable Schema | P0 | 必填、类型、默认值校验 |
| B-03 | Prompt Render Service | P0 | 安全渲染与注入测试 |
| B-04 | Prompt Preview API | P0 | 仅渲染不调用模型 |
| B-05 | Prompt Diff | P1 | 文本与变量 Schema 差异 |
| B-06 | Prompt 管理 UI | P0 | CRUD、版本、预览完整 |

### EPIC C — Tool / Resource Binding

| ID | 任务 | 优先级 | 验收 |
|---|---|---:|---|
| C-01 | Tool Catalog Query | P0 | 仅展示可见且启用 Tool |
| C-02 | Binding Validator | P0 | 未授权 Tool 无法保存/发布 |
| C-03 | KB / Model / Memory Binding | P0 | 资源授权与引用校验 |
| C-04 | Binding Snapshot | P0 | 发布后引用稳定 |
| C-05 | 高风险 Tool 规则 | P0 | 缺审批策略不能进入生产 |

### EPIC D — Playground

| ID | 任务 | 优先级 | 验收 |
|---|---|---:|---|
| D-01 | Playground Session API | P0 | 测试会话隔离 |
| D-02 | Sandbox Policy | P0 | 强制 Mock/只读策略 |
| D-03 | Runtime Facade Integration | P0 | 只通过 V1.1 Facade 调用 |
| D-04 | Run Event SSE | P0 | 断线可恢复查询 |
| D-05 | Debug Detail Aggregator | P1 | Tool/RAG/Prompt/Context Trace |
| D-06 | Playground UI | P0 | 可完成完整调试流程 |
| D-07 | Cost / Rate Limit | P0 | 单次与用户配额生效 |

### EPIC E — Evaluation

| ID | 任务 | 优先级 | 验收 |
|---|---|---:|---|
| E-01 | Dataset / Version / Case | P0 | Dataset Version 不可变 |
| E-02 | Evaluation Profile | P0 | 指标与 Gate 配置版本化 |
| E-03 | Job Queue / Worker | P0 | 异步执行、取消、重试 |
| E-04 | Agent Runner Adapter | P0 | 通过 Runtime Facade 执行 |
| E-05 | Deterministic Scorers | P0 | 断言可复现 |
| E-06 | 最小 Semantic Scorer | P0 | 至少一种语义评分，固定版本/结构；必选评分失败不判 Gate 通过 |
| E-07 | Result / Report | P0 | 逐样本 Trace 和指标 |
| E-08 | Version Compare | P1 | 同 Dataset/Profile 可比 |
| E-09 | Evaluation UI | P0 | Dataset、Run、结果和报告 |
| E-10 | RAGAS Adapter / Profile 接入 | P0 | 适用 RAG 指标映射、版本与错误处理冻结；与确定性断言分工 |
| E-11 | 额外 Judge / 评分器校准 | P1 | 新增指标和校准不改变历史评分口径 |

### EPIC F — Release & Governance

| ID | 任务 | 优先级 | 验收 |
|---|---|---:|---|
| F-01 | Publish Validator | P0 | 发布前完整校验 |
| F-02 | Evaluation Gate | P0 | 硬门禁失败阻止发布 |
| F-03 | Atomic Version Switch | P0 | 并发发布无覆盖 |
| F-04 | Rollback | P0 | 回滚生成事件，不修改旧版本 |
| F-05 | Suspend / Resume | P1 | 暂停后新 Run 被阻断 |
| F-06 | Release History UI | P1 | 可查变更与评测报告 |
| F-07 | Audit Integration | P0 | 关键操作不可缺审计 |

### EPIC G — Chat / Admin Integration

| ID | 任务 | 优先级 | 验收 |
|---|---|---:|---|
| G-01 | Admin Agent List | P0 | 搜索、筛选、权限 |
| G-02 | Agent Editor UI | P0 | 受控表单编辑 |
| G-03 | Role Permission Integration | P0 | 后端按规范矩阵鉴权；publish/operate 分离，回滚/暂停/恢复负向测试通过 |
| G-04 | Chat Agent Directory | P1 | 仅展示已发布且授权 Agent |
| G-05 | Agent Version Pinning | P0 | Run 固定版本 |
| G-06 | Trace Link Integration | P1 | 复用既有 Trace 权限 |

### EPIC H — Quality / Security / Delivery

| ID | 任务 | 优先级 | 验收 |
|---|---|---:|---|
| H-01 | Unit / Integration / Contract Tests | P0 | CI 通过 |
| H-02 | Authorization Matrix Tests | P0 | 无越权访问 |
| H-03 | Prompt Injection / Data Leakage Tests | P0 | 严重用例通过 |
| H-04 | Load / Cost Tests | P1 | 达到项目基线 |
| H-05 | Migration / Rollback Tests | P0 | Definition/Run 身份与版本、eval_* 数据映射可升级且兼容 |
| H-06 | OpenAPI / Schema Docs | P0 | 与实现一致 |
| H-07 | Deployment / Runbook | P0 | 可部署、可恢复 |

## 6. Definition of Done

任何 P0 任务完成必须同时满足：
- 代码合并且 Review 通过。
- 单元与相关集成测试通过。
- API / Event / Schema Contract 更新。
- 权限、审计、错误处理和日志完整。
- 有运行文档和必要监控。
- 不引入绕过 Policy / Gateway 的路径。
- 数据迁移具备验证和回滚方案。
- 前后端功能在目标环境联调通过。

## 7. CI/CD 门禁

建议流水线：
1. Format / Lint / Type Check
2. Unit Tests
3. Schema / OpenAPI Contract Tests
4. Integration Tests（PostgreSQL、Redis、RabbitMQ）
5. Security Tests（依赖扫描、秘密扫描、权限测试）
6. Frontend Build / E2E Smoke
7. Migration Compatibility Test
8. Image Build / SBOM
9. Staging Deploy + Smoke
10. 发布审批与生产部署

## 8. V1.2 技术风险清单

| 风险 | 影响 | 缓解 |
|---|---|---|
| Definition 过度自由 | 权限与运行不可控 | 声明式 Schema、白名单模板 |
| 版本快照不完整 | 运行不可复现 | Snapshot Builder + 引用校验 |
| Playground 触达生产写操作 | 数据破坏 | 服务端 Sandbox Policy |
| Judge 不稳定 | 发布误判 | 确定性断言 + Judge 版本固定 |
| 评测挤占在线资源 | Chat 延迟上升 | 独立 Worker 队列与配额 |
| Agent 权限膨胀 | 数据泄露 | Policy Engine 最终授权 |
| Prompt / Tool / KB 漂移 | 行为不一致 | 版本绑定和发布门禁 |
| 回滚无法恢复 | 生产故障 | 不可变版本与原子指针切换 |

## 9. V1.2 交付清单

- 后端模块与数据库迁移
- Agent Definition JSON Schema
- Agent / Prompt / Evaluation / Release API
- Admin Agent Builder、Prompt、Playground、Evaluation 页面
- Chat 已发布 Agent 入口
- Golden / Adversarial Dataset 初始集合
- 自动化测试与发布 Gate
- 运行手册、故障处理手册、权限矩阵
- OpenAPI、Schema 和 ADR 更新
