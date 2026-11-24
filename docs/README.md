# 项目文档索引

文档按用途分类。版本包保留本版详细设计、任务拆分与验收标准，跨版本共用的架构、契约和开发规范集中维护。

```text
docs/
├── README.md
├── plan/             # 总体路线图与 V1.0–V2.0 版本包
├── architecture/     # 技术架构、统一契约与术语
├── standards/        # 前后端规范、Git 提交与协作规范
├── adr/              # 架构决策记录
└── reviews/          # 当前修订进度与历史审查档案
```

## 按用途查阅

| 分类 | 阅读入口 | 用途 |
|---|---|---|
| 计划与版本包 | [总体版本路线图与架构演进规划](plan/总体版本路线图与架构演进规划.md) | 确认交付范围、版本依赖与进入/退出条件，再查对应版本包 |
| 架构与契约 | [技术架构文档](architecture/技术架构文档.md)、[统一契约与跨版本演进规则](architecture/统一契约与跨版本演进规则.md)、[术语表](architecture/GLOSSARY.md) | 确认分层、技术基线、公共实体与兼容规则 |
| 开发规范 | [前端代码规范](standards/前端代码规范.md)、[后端代码规范](standards/后端代码规范.md)、[Git 提交规范](standards/git-提交规范.md)、[Git 协作规范](standards/git-协作规范.md) | 初始化或修改前后端、提交、创建分支/PR 或评审时查阅对应规范 |
| 架构决策 | [单一企业内部部署范围](adr/0013-single-enterprise-deployment-scope.md)、[Monorepo 与独立前端应用](adr/0014-monorepo-and-independent-frontend-apps.md)、[RustFS 对象存储](adr/0015-rustfs-object-storage.md) | 查阅已确认方案；其余 ADR 按任务读取，并核对各自状态 |
| 修订与审查 | [文档修订与收敛记录](reviews/文档修订与收敛记录.md)、[历史审查索引](reviews/README.md) | 前者跟踪当前处理结果与剩余验收；后者用于追溯历史争议和原文证据 |

## 版本包

| 版本 | 主要目标 | 开发入口 |
|---|---|---|
| V1.0 MVP | 建立企业知识问答基础 | [版本说明](plan/V1.0-MVP/README.md)、[完整研发实施计划与阶段验收标准](plan/V1.0-MVP/06-完整研发实施计划与阶段验收标准.md) |
| V1.1 Agent Platform Foundation | 建立 Agent 执行与工具调用底座 | [版本说明](plan/V1.1-Agent-Platform-Foundation/README.md)、[实施计划与验收](plan/V1.1-Agent-Platform-Foundation/06-complete-implementation-plan-and-acceptance.md) |
| V1.2 Agent Development Platform | 配置、测试和发布 Agent | [版本说明](plan/V1.2-Agent-Development-Platform/README.md)、[实施计划与验收](plan/V1.2-Agent-Development-Platform/06-complete-implementation-plan-and-acceptance.md) |
| V1.3 Advanced Agentic AI | 增量建设规划、协作与 Agentic RAG | [版本说明](plan/V1.3-Advanced-Agentic-AI/README.md)、[实施计划与验收](plan/V1.3-Advanced-Agentic-AI/07-complete-implementation-plan-and-acceptance.md) |
| V1.4 Enterprise Workflow and Integration | 企业流程、审批与生产连接器 | [版本说明](plan/V1.4-Enterprise-Workflow-and-Integration/README.md)、[实施计划与验收](plan/V1.4-Enterprise-Workflow-and-Integration/08-complete-implementation-plan-and-acceptance.md) |
| V2.0 Enterprise-Grade Platform | 企业运营、高可用、预算与灾备 | [版本说明](plan/V2.0-Enterprise-Grade-Platform/README.md)、[实施计划与验收](plan/V2.0-Enterprise-Grade-Platform/09-complete-implementation-plan-and-acceptance.md) |

## 阅读与维护

首次开发按 [AGENTS.md](../AGENTS.md) 的任务顺序执行，先确认目标版本，再读取对应规范、详设与实施计划。新增版本设计放入对应版本包；跨版本规则、工程规范、决策和审查材料分别放入相应分类。移动文档时同步更新本索引、AGENTS.md 和文档间引用。

版本范围以总体路线图为准，公共契约按统一契约规则解释，已批准的 ADR 管理相关基线变更。历史审查材料用于追溯；草案和文档勾选的实施状态须由实际验收证据确认。
