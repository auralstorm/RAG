# Enterprise Agentic AI Platform

> 公共字段、状态、事件、权限与迁移映射见 [统一契约与跨版本演进规则](../../architecture/统一契约与跨版本演进规则.md)；本文件描述本版能力及增量，具体实现须通过契约与升级验收。
# POC 技术验收与 ADR 冻结

- 文档版本：V1.0
- 日期：2026-11-23
- 状态：POC 计划与决策记录基线（尚未表示 POC 已通过）

## 1. POC 目的

POC 的任务是验证既定默认技术方案能否满足项目硬性要求，而不是重新开放无限制技术选型。若默认方案通过验收，冻结为项目基线；只有出现可复现的硬性不满足项，才通过 ADR 提出替换或调整。

**当前状态：技术基线已选定，尚无证据表明下列 POC 已全部执行并通过。** 任何性能阈值、解析质量、成本或兼容性结论必须以实际测试记录为准。

## 2. 基线与待验证项

| 领域 | 默认基线 | 主要验证问题 | 备选 |
|---|---|---|---|
| Backend | Python + FastAPI | API、SSE、异步集成、团队熟悉度 | 不预设 |
| Frontend | React + TypeScript | Chat/Admin 复杂交互 | 不预设 |
| RAG | LlamaIndex | Pipeline 可控性、组件适配、升级风险 | 自研薄编排层 |
| Agent | LangGraph | State、Checkpoint、Resume、Tool 调用 | 自研有限状态机（仅若硬性不满足） |
| Parser | Docling | PDF/Office/表格解析质量、性能 | MinerU 复杂 PDF |
| Search | Elasticsearch | Dense + BM25 + ACL + RRF + 性能 | OpenSearch |
| Model Gateway | 自研 Facade + LiteLLM | Provider 适配、限流、重试、流式、Embedding | 扩展自研 Adapter |
| Async | RabbitMQ + Celery | 幂等、重试、恢复、监控 | 需 ADR 才调整 |
| DB | PostgreSQL | 事务、迁移、JSONB、并发写 | 不预设 |
| Cache | Redis | 缓存、限流辅助、短期状态 | 不预设 |
| Object | S3 compatible / MinIO | 大文件、生命周期、并发上传 | 兼容 S3 服务 |
| Observability | OTel + Phoenix | Trace/Span、脱敏、检索诊断 | OTel Collector + 其他 UI |
| Evaluation | RAGAS + Golden Dataset | 指标可解释性、重复性 | 自定义评测器补充 |

## 3. POC 测试原则

1. 使用真实代表性数据样本，覆盖正常、边界和失败样本。
2. 固定硬件、版本、配置和数据集，保证可复现。
3. 每项测试保存脚本、输入数据版本、日志、Trace、结果和结论。
4. 同时测正确性、可靠性、安全性、可运维性和成本。
5. 不只测单次 Happy Path；要测试超时、限流、重试、故障恢复和权限撤销。
6. 以业务 SLO 为目标设门槛；门槛由产品/技术负责人在测试前确认。
7. POC 结果为 PASS / CONDITIONAL PASS / FAIL；Conditional Pass 必须有责任人、期限和风险接受记录。

## 4. POC-01 Elasticsearch Hybrid Search

### 4.1 验证目标
- Dense 与 BM25 独立召回、Hybrid 融合和 Metadata / ACL Filter 可用。
- 向量维度、字段映射、索引版本和 alias 切换可控。
- ACL Filter 在召回阶段执行，权限撤销后无越权窗口。
- 查询吞吐、延迟、索引构建和更新符合项目确认的目标。

### 4.2 测试集
- 至少覆盖短问句、长问句、关键词精确匹配、语义同义表达、数字/编号、表格字段、跨段问题。
- 包含有权/无权文档、不同 KB、文档撤销、已删除文档。
- 数据规模分为小规模开发集和接近目标容量的压测集；规模由项目确认，不在本文件臆造。

### 4.3 测试用例
- ES-01：Dense Top-K 正常召回，记录 Recall@K。
- ES-02：BM25 对精确术语/编号召回。
- ES-03：Hybrid + RRF 对比 Dense-only / BM25-only。
- ES-04：Metadata Filter 正确排除不匹配数据。
- ES-05：ACL Filter 对无权限数据零泄露。
- ES-06：权限撤销后查询不可见。
- ES-07：向量维度错误时写入失败并可诊断。
- ES-08：新索引构建、验证、alias 原子切换和回滚。
- ES-09：并发查询与批量写入下测量 P50/P95/P99、错误率和资源占用。
- ES-10：节点/服务异常后的恢复行为。

### 4.4 通过标准
- 功能正确性与 ACL 安全用例全部通过。
- Hybrid 对目标 Golden Dataset 的质量达到事先约定门槛。
- 索引发布/回滚可重复且不破坏在线查询。
- 性能指标达到测试前签署的目标；不得以单次测试结果替代稳定压测。

## 5. POC-02 Docling / MinerU Parser

### 5.1 样本
- 数字 PDF、扫描 PDF、混合 PDF、双栏排版、复杂表格、页眉页脚、图片标题、DOCX、PPTX（按产品实际格式范围）。
- 对样本建立人工校验基准：标题层级、正文、表格内容、页码、阅读顺序。

### 5.2 测试
- 解析成功率、关键字段/表格保真度、阅读顺序、页码定位。
- CPU / GPU（如适用）资源、耗时、内存峰值。
- 相同文件重复解析结果稳定性。
- 超大文件、损坏文件、加密文件、异常编码的错误行为。
- 对复杂 PDF 比较 Docling 与 MinerU，决定是否按规则路由。

### 5.3 通过标准
- 关键内容抽取达到业务确认阈值。
- 失败能明确返回 Parser Error，不生成看似成功的空索引。
- Parser Adapter 输出统一 ParsedDocument，不把 Parser 专有结构泄漏到业务层。

## 6. POC-03 LlamaIndex RAG Pipeline

验证：
- Parser 输出、Node/Chunk、Metadata、Retriever、Postprocessor、Query Pipeline 的接入方式。
- 是否能控制 ACL Filter、Hybrid Retrieval、Reranker、Parent Expansion、Token Budget。
- Trace 与平台业务 ID 是否能贯穿。
- 组件升级是否影响平台 Contract。
- 性能和可测试性是否满足要求。

通过标准：LlamaIndex 作为组件使用，不要求平台核心领域模型依赖 LlamaIndex 类型；所有关键阶段可被替换、观测和单测。

## 7. POC-04 Model Gateway Facade + LiteLLM

验证：
- 至少一种 Chat 模型、一种 Embedding 模型；Reranker 如选用独立模型也需验证。
- 非流式、流式、Embedding 批量调用、错误映射。
- 用户/模型/系统级速率与并发限额，验证缓存故障下的保守准入。
- 超时、429、5xx、供应商不可用、Fallback。
- Token 统计与费用估算字段完整性。
- API Key 加密、掩码和权限隔离。
- 不同模型 Capability Registry 与真实能力一致。

通过标准：上层 RAG / Agent 只调用平台 Model Gateway Contract，不直接持有供应商 Key 或配置 LiteLLM 内部细节。

## 8. POC-05 RabbitMQ + Celery

验证：
- 任务重复投递、Worker 崩溃、任务超时、Broker 短暂不可用。
- 幂等键防重复产物。
- Retry / Backoff / Dead Letter 或失败队列。
- 从中间阶段恢复，不重复执行已成功的昂贵步骤。
- Worker 水平扩容时任务状态一致。
- 任务进度和错误可在 Admin 查询。

通过标准：重复投递不导致重复业务数据；任务最终状态可解释；失败可恢复或明确终止。

## 9. POC-06 OpenTelemetry + Phoenix

验证：
- FastAPI → Celery → Parser / Embedding → ES → Model Gateway 的 Trace Context 传播。
- 每次 Chat 一个 Trace，多 Span 可关联。
- Token、耗时、错误、检索结果和模型版本可观测。
- 敏感字段脱敏；默认 Trace 匿名。
- Phoenix UI 与平台 Trace 查询 API 的数据关联。
- 身份映射独立存储；高危溯源权限可审计。

通过标准：能够通过 TraceId 定位一次问答的关键链路和失败阶段；无未经授权的身份暴露。

## 10. POC-07 端到端闭环

场景：管理员创建 KB → 配置模型 → 上传文档 → 异步解析与索引 → 发布 → 员工 OAuth 登录 → 提问 → 收到流式答案与真实引用 → Trace 诊断 → Golden Dataset 回归 → 修改配置并发布 → 回滚验证。

通过标准：
- 每一步状态与错误可见。
- ACL 全程有效。
- 删除与离职生命周期规则有效。
- 可复现质量对比。
- 失败时旧版本仍可用或系统明确拒答，不出现静默数据损坏。

## 11. POC 结果记录模板

每项测试必须记录：

| 字段 | 内容 |
|---|---|
| POC ID | 唯一编号 |
| 测试负责人 | 姓名/团队 |
| 测试日期 | UTC 时间 |
| 软件版本 | 完整版本号 |
| 环境 | CPU / RAM / ES 节点 / 网络等 |
| 数据集版本 | 样本来源与 Hash |
| 配置 | 完整参数 |
| 测试步骤 | 可复现步骤 |
| 预期结果 | 测试前定义 |
| 实际结果 | 原始数据和指标 |
| 证据 | 日志、Trace、截图、脚本链接 |
| 结论 | PASS / CONDITIONAL PASS / FAIL |
| 风险与 Action | 责任人、截止日期 |

## 12. ADR 冻结流程

1. 记录问题：当前基线哪个硬性要求不满足。
2. 提供证据：POC 结果、性能数据、安全问题、运维成本。
3. 列出可选方案：至少说明维持基线、局部适配、替换方案。
4. 比较影响：业务、架构、数据迁移、成本、团队能力、运维、锁定风险。
5. 明确决策：Accepted / Rejected / Superseded。
6. 评估迁移与回滚路径。
7. 技术负责人、架构负责人和相关业务负责人审批。
8. 更新技术基线版本及受影响文档。

### 12.1 ADR 模板

```markdown
# ADR-NNNN: 标题
- 状态：Proposed / Accepted / Rejected / Superseded
- 日期：
- 决策人：

## Context
当前问题、约束、硬性需求。

## Decision Drivers
性能、安全、质量、成本、运维、团队能力等。

## Options
A. 保持当前基线
B. 适配当前基线
C. 替换技术

## Decision
选择与明确边界。

## Evidence
POC 编号、数据、链接。

## Consequences
正面影响、负面影响、迁移成本、运维变化。

## Rollback
回滚条件和步骤。
```

## 13. 初始 ADR 记录

### ADR-0001：RAG 框架采用 LlamaIndex
- 状态：Accepted（项目技术基线决策；集成细节待 POC）
- 决策：LlamaIndex 用于 Ingestion / Retriever / Pipeline 组件。
- 边界：平台自有 Document、Chunk、ACL、Index Version、API Contract、Citation、Trace 等核心模型。
- 依据：提高组件复用效率，同时避免框架成为业务数据模型。
- 重审条件：ACL、Hybrid、Pipeline 控制能力无法满足硬性要求，或升级兼容性造成不可接受风险。

### ADR-0002：Agent Runtime 采用 LangGraph
- 状态：Accepted（V1.1 启用单 Agent 底座；V1.3 扩展高级执行，V1.0 不做复杂 Agent）
- 决策：LangGraph 作为状态图、Checkpoint、Retry、审批编排基础。
- 边界：AgentRun / Step / Version / Tool / Audit 为平台业务模型。
- 重审条件：Checkpoint 恢复、并发控制或状态迁移无法满足硬性要求。

### ADR-0003：Search 默认 Elasticsearch
- 状态：Accepted（最终部署版本与参数待 POC）
- 决策：ES 作为默认搜索引擎；Dense + BM25 + Hybrid + ACL Filter。
- 边界：通过 Search Adapter 隔离，OpenSearch 保留候选。
- 重审条件：POC 证明 ES 在关键功能、性能或成本上无法满足目标且 OpenSearch 有可复现优势。

### ADR-0004：Parser 默认 Docling，MinerU 作为复杂 PDF 备选
- 状态：Accepted（样本质量待 POC）
- 决策：统一 Parser Adapter 与 ParsedDocument Contract。
- 重审条件：代表性文档集解析质量或性能不达标。

### ADR-0005：Model Gateway 自研 Facade + LiteLLM
- 状态：Accepted
- 决策：平台自有统一模型 API 和业务治理，LiteLLM 提供底层 Provider Proxy/适配。
- 边界：平台负责模型注册、权限、业务限流、审计和能力注册。
- 重审条件：关键 Provider 能力缺失或代理层无法满足可靠性要求。

### ADR-0006：模块化单体作为 MVP 部署形态
- 状态：Accepted
- 决策：FastAPI 模块化单体 + 独立 Celery Worker；按边界拆包，不全面微服务化。
- 重审条件：明确的团队/容量/隔离需求证明拆分服务的净收益。

## 14. 冻结清单

POC 完成后，技术负责人需冻结：
- 具体版本矩阵与容器镜像 Tag。
- ES Mapping、向量维度、索引模板和 Alias 策略。
- Parser 路由规则。
- Embedding / Reranker / Chat 模型及 Capability。
- Chunking 参数、RAG 参数、Prompt 版本。
- Celery 队列、重试和超时策略。
- Trace Schema 与脱敏规则。
- 数据保留、备份、删除和恢复策略。
- P95 / 并发 / 吞吐 / 质量 SLO。
