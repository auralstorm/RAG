# Enterprise Agentic AI Platform

> 公共字段、状态、事件、权限与迁移映射见 [统一契约与跨版本演进规则](../../architecture/统一契约与跨版本演进规则.md)；本文件描述本版能力及增量，具体实现须通过契约与升级验收。
# POC 技术验收与 ADR 冻结

- 文档版本：V1.0
- 日期：2026-11-24（记录 RustFS 替换决策与分阶段验证）
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
| Object | RustFS / S3 compatible（ADR-0015，生产准入待 POC） | 大文件、生命周期、并发上传及 POC-08 的维护/安全问题 | 经验证的兼容 S3 服务 |
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

### 4.5 Basic 许可下的 RRF 实现与执行状态

2026-11-24 实测当前 Elasticsearch `9.2.0` 为有效 Basic 许可，原生 RRF 返回 HTTP 403，原因是 `current license is non-compliant for [Reciprocal Rank Fusion (RRF)]`。用户已批准保持 ES 基线，在 Search Adapter 内执行排名融合，依据 [ADR-0016](../../adr/0016-client-side-rrf-under-basic-license.md)。Dense 与 BM25 都在召回前执行可信当前授权和状态过滤，alias 每次解析到唯一物理索引，失败/部分响应拒绝返回。

[POC-01 实施记录](implementation/POC-01-search.md) 与 `make poc-search` 提供独立真实服务、合成向量与权限夹具的功能证据；完整业务质量、容量、实际权限集成和非作者安全评审仍待完成，不能据此关闭 POC-01。全部 P0-03 输入和状态见 [实施进度](implementation/P0-03.md)。

## 5. POC-02 Docling 基础解析与按需 PDF 对比

**执行决定（2026-11-24 更新）：** 用户明确将独立 POC-02 延后，先回归 V1.0 主线开发；下列解析验证合并到 [P3-01 Parser Adapter 与 Docling 正式集成](06-完整研发实施计划与阶段验收标准.md#p3-01-parser-adapter-与-docling-集成)，不再作为 P0-04/05 和不依赖 Parser 的 P1 工作的前置阻塞。当前状态为延后待验收，不能标记为通过或据此关闭完整 P0-03/M0。Docling 仍为默认 Parser，首期 Markdown、DOCX、PDF 的内容质量、定位、错误和资源验收要求保留。MinerU 保留为 PDF 备选；发现 Docling 对实际样本存在明确缺口后，再开展同样本对比并决定是否接入。

### 5.1 样本
- 首期覆盖 Markdown、DOCX、PDF；PDF 以目标业务样本为准，记录数字/扫描/混合、双栏、复杂表格、页眉页脚及图片标题等特征。PPTX 等其他格式按后续已确认范围增加。
- 对样本建立人工校验基准：标题层级、正文、表格内容、页码、阅读顺序。

### 5.2 测试
- 解析成功率、关键字段/表格保真度、阅读顺序、页码定位。
- CPU / GPU（如适用）资源、耗时、内存峰值。
- 相同文件重复解析结果稳定性。
- 超大文件、损坏文件、加密文件、异常编码的错误行为。
- 先记录 Docling 在目标样本上的正文/标题/页码、阅读顺序、表格单元格与合并关系、错误、耗时和资源使用；不以“解析成功”替代内容正确性验收。
- Docling 出现漏内容、表格错位、阅读顺序或引用定位错误、耗时不达已确认门槛时，保留失败样本、版本、参数及日志，先核对 Docling 配置/OCR/Adapter；缺口仍存在时再用同一批样本比较 MinerU 的质量、耗时与部署成本。

### 5.3 通过标准
- 关键内容抽取达到业务确认阈值。
- 失败能明确返回 Parser Error，不生成看似成功的空索引。
- Parser Adapter 输出统一 ParsedDocument，不把 Parser 专有结构泄漏到业务层。
- 当前验收针对 Docling；MinerU 记录为“保留备选、未启用/未验收”，不将缺少 MinerU 对比作为当前 POC 的前置阻塞，也不标记为通过。Docling 未满足首期必需内容质量时继续修复或按上述条件启动备选验证。

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

场景：管理员创建 KB → 配置模型 → 上传文档 → 异步解析与索引 → 发布 → 员工使用平台账号登录 → 提问 → 收到流式答案与真实引用 → Trace 诊断 → Golden Dataset 回归 → 修改配置并发布 → 回滚验证。外部身份源后续接入时沿用此流程，不作为 V1.0 平台账号验收前提。

通过标准：
- 每一步状态与错误可见。
- ACL 全程有效。
- 删除与离职生命周期规则有效。
- 可复现质量对比。
- 失败时旧版本仍可用或系统明确拒答，不出现静默数据损坏。

## 11. POC-08 对象存储维护、安全与选型复核

### 11.1 已确认问题与证据

2026-11-24 核验发现以下问题。**问题状态：已确认；选型决策：用户已批准 RustFS 替换，见 [ADR-0015](../../adr/0015-rustfs-object-storage.md)；POC 状态：部分执行，未关闭。** P0-02 的功能与持久化测试结果保留，不能据此认定对象存储通过安全和长期维护准入。

| 问题 | 已核验事实与来源 | 对当前项目的影响 |
|---|---|---|
| 社区服务端停止维护 | [官方 README](https://github.com/minio/minio#readme) 明确声明 `THIS REPOSITORY IS NO LONGER MAINTAINED`；[仓库元数据](https://api.github.com/repos/minio/minio) 的 `archived` 为 true | 不能继续假定社区服务端会获得官方公开安全修复、版本更新和维护支持；需复核长期维护路径 |
| 镜像获取失败与分发变化 | P0-02 中 Docker Hub 返回 `pull access denied`，Quay 返回 `401 Unauthorized`；官方 README 说明社区版本采用源码分发，停止提供预编译版本 | 错误直接证明当时镜像地址无法获取，不能单凭报错断言归档是唯一原因；源码构建恢复了获取能力，后续修复和构建维护仍需明确责任 |
| 原版本早于安全修复 | P0-02 原固定 `RELEASE.2025-09-07T16-13-09Z`；[官方安全公告](https://github.com/minio/minio/security/advisories/GHSA-jjjj-jwhf-8rgr) 披露高风险 `CVE-2025-62506`，Service Account / STS Session Policy 存在权限提升问题，[修复版本](https://github.com/minio/minio/releases/tag/RELEASE.2025-10-15T17-29-55Z) 为 `RELEASE.2025-10-15T17-29-55Z` | 当前版本需要修复/升级评估与安全回归，不能直接冻结为生产使用版本；采用最后修复版本也不能恢复官方长期维护 |

原 P0-02 实现见 [MinIO Dockerfile](../../../infra/docker/minio/Dockerfile)、[镜像配置](../../../infra/compose/images.env) 与 [P0-02 实施记录](implementation/P0-02.md)。原镜像由固定官方源码、源码 SHA-256、固定 Go/Alpine 基础镜像构建；这些措施保证构建输入可核验，源码构建本身不修复旧版本漏洞。

### 11.2 方案比较与已批准决定

- **已选择 RustFS：** 用户在 [2026-11-24 一手资料研究](research/rustfs-object-storage.md) 后明确批准替换，采用 `1.0.6` 固定镜像摘要与独立新卷，保持 S3 Adapter 与平台资源 ACL 边界；[ADR-0015](../../adr/0015-rustfs-object-storage.md) 记录取舍，[实施记录](implementation/rustfs-object-storage.md) 记录本次运行、兼容和回退证据。选型确认不代表生产准入通过。
- **短期更新社区源码版本：** 至少评估已知 CVE 的修复版本与适用回归。若继续自维护社区源码，记录源码/依赖修复责任、响应方式、成本和有期限的风险接受条件。
- **评估官方 AIStor Free / Enterprise：** 官方推荐的后续方案，须核实实际授权、部署方式、功能限制、升级路径、支持和成本；不将“免费”视为开源或已批准的生产授权。
- **评估其他持续维护的 S3 兼容实现：** 验证其维护情况和真实协议行为，部署范围仍遵循已确认的单企业模式。候选名称和方案比较不代表基线已经变更。

### 11.3 验证用例

- OBJ-01：核对候选的官方维护/发布状态、安全公告、支持路径、授权和更新机制，记录版本与来源。
- OBJ-02：对当前已知漏洞及受影响配置进行安全回归；验证 Service Account、STS Session Policy 和受限凭据不能扩大桶、对象前缀或读写权限。安全关键结论须由非作者 Reviewer 审查。
- OBJ-03：验证 S3 签名认证、桶与对象创建/查询/读取/删除、对象内容与元数据一致性；权限拒绝和错误语义可解释。
- OBJ-04：验证预签名 URL 的有效期、篡改/越权拒绝、多段上传、大文件和并发行为；规模与门槛按 MVP 确认值记录。
- OBJ-05：验证服务故障、重建、备份/恢复、删除和生命周期规则，核对对象数量、键、内容校验值及配置。
- OBJ-06：验证可维护的镜像/源码构建、版本升级和回滚，记录依赖、安全修复和运维成本；配置及日志不暴露凭据。
- OBJ-07：盘点现有桶、对象和策略，评估 `infra/compose`、初始化脚本、配置、SDK Adapter、就绪探针和测试的适配；形成迁移与回滚方案，保持平台业务模型与 S3 供应商隔离。

### 11.4 关闭条件与执行顺序

Tech Lead / Platform 在 **P0-03 对象存储版本与 M0 技术基线冻结前** 完成验证和方案比较，提交真实证据及维护、安全、授权、兼容与成本结论。

- 当前旧版本的已知漏洞及长期维护问题均有明确处置；仅能启动、上传/下载或通过 P0-02 测试不能关闭本问题。
- 必需安全用例与适用兼容/生命周期验证通过；缺少证据时保持待验证，有条件通过须记录负责人、期限和风险接受。
- 保留、更新或替换方案有具体维护路径、迁移/回滚依据与决策记录；基线变更按 ADR 流程和用户已确认范围执行。
- 同步源码/镜像、SDK、配置、测试和相关文档后，才冻结对象存储交付基线。对象存储选型已确认；下述开发验收不替代完整 POC 关闭条件。

### 11.5 RustFS 开发基线替换与待验收项

开发/测试采用官方 RustFS `1.0.6`（固定 digest），S3 客户端仍为维护中的 `minio==7.2.20` Python SDK。此次盘点源桶无对象、无版本历史、未启用版本、无桶策略，使用新卷启动；原 MinIO 卷与 0600 凭据备份保留。全部实际检查结果和回退边界见 [替换实施记录](implementation/rustfs-object-storage.md)，研究原文作为选型时证据保留。

开发切换检查覆盖配置兼容、基础 S3、预签名与多段上传的部分 OBJ-03/04、容器故障/重建和空桶切换回退的部分 OBJ-05/07。后续 [POC-08 功能验收](implementation/POC-08-storage.md) 通过 `make poc-storage` 验证 OBJ-02 的受限身份/Service Account/STS 权限边界、加速生命周期下的实际 payload 回收，以及当前对象与元数据的空新卷恢复和显式策略重建，共 9 项测试通过。

OBJ-02 的非作者安全评审、OBJ-04 的实际浏览器 CORS 和规模并发、OBJ-05 的生产保留期/版本/完整 IAM 与加密恢复、OBJ-06 的制品扫描/签名和目标拓扑升级演练仍待 P0-03 执行，负责人按 Tech Lead / Platform 分工，在 M0 冻结前完成；未设定或未实测的门槛不得填写为 PASS。

## 12. POC 结果记录模板

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

## 13. ADR 冻结流程

1. 记录问题：当前基线哪个硬性要求不满足。
2. 提供证据：POC 结果、性能数据、安全问题、运维成本。
3. 列出可选方案：至少说明维持基线、局部适配、替换方案。
4. 比较影响：业务、架构、数据迁移、成本、团队能力、运维、锁定风险。
5. 明确决策：Accepted / Rejected / Superseded。
6. 评估迁移与回滚路径。
7. 技术负责人、架构负责人和相关业务负责人审批。
8. 更新技术基线版本及受影响文档。

### 13.1 ADR 模板

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

## 14. 初始 ADR 记录

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
- 状态：Accepted（样本质量待 POC；2026-11-24 用户确认 Docling 优先、MinerU 按实际缺口验证）
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

## 15. 冻结清单

POC 完成后，技术负责人需冻结：
- 具体版本矩阵与容器镜像 Tag。
- 对象存储的维护/支持路径、授权、安全修复状态及 POC-08 的处置决策。
- ES Mapping、向量维度、索引模板和 Alias 策略。
- Parser 路由规则。
- Embedding / Reranker / Chat 模型及 Capability。
- Chunking 参数、RAG 参数、Prompt 版本。
- Celery 队列、重试和超时策略。
- Trace Schema 与脱敏规则。
- 数据保留、备份、删除和恢复策略。
- P95 / 并发 / 吞吐 / 质量 SLO。
