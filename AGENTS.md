# AI 开发规范

完整文档与版本包入口见 [文档索引](docs/README.md)。

## 项目范围

- 用户未指定版本的新开发任务默认按 V1.0 MVP 推进；按对应版本的范围、依赖与 Exit Criteria 判断交付，不提前实现后续版本能力。
- 所有版本采用单一企业内部部署，依据 [ADR-0013](docs/adr/0013-single-enterprise-deployment-scope.md)；部门、团队、KB、Workspace 按企业内身份与资源 ACL 授权，不新增客户租户实体或迁移预留。
- 工程目录和技术栈沿用已确认基线，实际实现、依赖版本与运行能力以源码、锁文件和验证证据为准。

## 工程基线

- 同一 Monorepo 管理前后端、基础设施与文档，依据 [ADR-0014](docs/adr/0014-monorepo-and-independent-frontend-apps.md)。
- 前端为 `frontend/apps/chat`（员工端）和 `frontend/apps/admin`（管理端）两个独立的 Vite + React + TypeScript 应用，使用 pnpm workspace，共用后端 API。
- 公共包位于 `frontend/packages/ui`、`api-client`、`shared`；应用依赖公共包，公共包不反向依赖应用，Chat/Admin 不直接导入彼此源码。
- 后端采用 FastAPI + uv、模块化单体与独立 Worker。普通知识问答默认走 Standard RAG；Agent 通过 Retriever API、Tool Gateway、Model Gateway 使用知识、工具和模型，框架/供应商 SDK 放在 Adapter 层。
- 资源授权由可信服务端计算，缺失必需授权上下文时拒绝访问；凭据使用安全引用，日志与 Trace 使用脱敏摘要。详细实现按下表读取。

## 任务阅读入口

1. **确认范围。** 功能开发先读 [总体路线图](docs/plan/总体版本路线图与架构演进规划.md) 的目标版本范围与验收，再读对应版本 README 和实施计划；V1.0 以 [完整研发实施计划](docs/plan/V1.0-MVP/06-完整研发实施计划与阶段验收标准.md) 为主线，初始化从 P0 开始。完成条件：任务输入、依赖、输出和验收场景明确。
2. **定位规则与实现。** 修改前按下表读取相关材料，检查实际模块、工作区改动、配置、锁文件与验证入口，保留用户已有改动。完成条件：修改位置与适用规则明确，设计与实现差异已核对。
3. **实现、验证并提交。** 完成相关实现、文档同步与验收检查；失败时继续定位修复。有实际改动的独立任务验收通过后，按 Git 提交规范立即创建本地提交，再开始下一项独立工作。完成条件：验收通过且已提交，或明确说明验证/提交阻塞与剩余事项。

| 任务触发条件 | 修改前必须读取 |
|---|---|
| 首次进入项目、初始化工程、调整模块或 workspace 边界 | [技术架构](docs/architecture/技术架构文档.md) 第 2/3/7 章；[V1.0 代码结构](docs/plan/V1.0-MVP/05-code-structure-and-backlog.md) 第 2 节及 ADR-0014 |
| 前端初始化或修改组件、Hook、状态、请求、样式、流式交互 | [前端代码规范](docs/standards/前端代码规范.md) |
| 后端初始化或修改 API、领域模块、数据访问、异步任务、异常、迁移 | [后端代码规范](docs/standards/后端代码规范.md) |
| 修改公共实体、字段、状态、事件、权限、删除生命周期或升级兼容 | [统一契约与跨版本演进规则](docs/architecture/统一契约与跨版本演进规则.md) 的相关章节，并核对实际 OpenAPI、JSON Schema 与迁移制品 |
| RAG、Ingestion、检索、上下文或引用 | [V1.0 RAG 详设](docs/plan/V1.0-MVP/01-rag-engine-detailed-design.md)；后续增量再查目标版本详设 |
| 数据库、身份或 API 设计 | [V1.0 数据库与 API](docs/plan/V1.0-MVP/03-database-and-api-design.md) 及目标版本的增量设计 |
| 技术选型、依赖升级、质量或性能门槛 | [POC 与 ADR](docs/plan/V1.0-MVP/04-poc-acceptance-and-adr.md) 及相关 ADR，使用可复现证据确定方案 |
| Agent、Tool、Memory、Registry、HITL、协作、Workflow 或企业运营 | 目标版本 README、实施计划、详设与统一契约相关章节；通过文档索引定位 |
| 确认术语或待验收问题 | [术语表](docs/architecture/GLOSSARY.md) 或 [文档修订与收敛记录](docs/reviews/文档修订与收敛记录.md) |
| 创建 Git 提交或编写提交信息 | [Git 提交规范](docs/standards/git-提交规范.md)，创建提交前必须读取 |
| 创建分支、PR 或进行代码评审 | [Git 协作规范](docs/standards/git-协作规范.md) |

## 决策与兼容

- 总体路线图管理版本范围，统一契约管理公共模型，已批准的 ADR 变更相关基线。架构 Phase 表示能力分层，不等同于实施阶段或需求优先级。
- 实际实现与设计不一致时，先调查存量结构、消费者与迁移成本，再形成兼容修改；草案、示例和任务勾选须由实施证据确认。[历史审查档案](docs/reviews/README.md) 仅在追溯变更原因时读取。
- 改变已确认技术基线、部署模式、版本范围或进行破坏性契约变更前，完成调查、影响与兼容方案，再将具体取舍交给用户确认；已有确认继续有效，常规修复和已授权实现持续推进。

## 验证与交付

- 用户已授权独立功能、修复、重构与文档任务验证通过后自动创建本地 Git 提交，无需逐次确认；用户明确要求暂不提交时遵从。只提交本任务改动，交付时报告提交 Hash、标题与验证结果；远程推送按用户的明确授权执行。
- 检查命令从实际 README、pyproject.toml、package.json、脚本与 CI 获取，按锁文件执行；统一安装、启动和检查入口见根 README。
- 按相关开发规范与版本验收计划验证受影响行为；公共包或 API 契约变化覆盖所有受影响消费者。纯文档改动检查路径、引用与示例，不补造业务测试。
- 相关检查通过后，仅因新变更、失败或未消除的问题扩大验证。交付说明包含实际变更、检查命令与结果、迁移/兼容影响及剩余事项，规划值和文档修订不作为实现验收证据。
