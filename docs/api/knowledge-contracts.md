# V1.0 知识资产、入库与索引契约

日期：2026-11-24。对应 P0-04-03。交付字段、版本关系、状态与纯规则；数据库、上传/解析/Worker、ES 原子切换及真实恢复在 P2/P3 执行。Docling 的实际验证继续按用户决定合并到 P3-01。

## 统一模型与消费者调查

此前没有实际 KB/Document/Job/IndexVersion 业务 DTO 或迁移，Search POC 的 Chunk 投影已有 document_id、document_version、kb_id 与 status=PUBLISHED。[知识契约](../../backend/app/modules/documents/domain/contracts.py) 将逻辑文档生命周期与具体版本处理分开；ES 的 PUBLISHED 投影语义保留，不把逻辑 Document 的 ACTIVE 状态直接写成检索发布状态。本轮无业务数据迁移、API 路径改名或外部服务写入。

| 原设计字段/语义 | 规范契约与兼容处理 |
|---|---|
| Document.version / documents.current_version | Document.current_version 为最新数值版本，可能尚未发布；在线版本从活动索引 Manifest 选择 |
| Document.status 中的 PARSING/FAILED/PUBLISHED 等 | 流程状态属于 DocumentVersion.status；Document.status 为 ACTIVE/DELETING/DELETED，控制所有版本的资源生命周期 |
| document_versions.id / version | 平台版本引用明确为 document_version_id / document_version；物理列和已有消费者在迁移时显式映射 |
| documents.object_key、文件 Hash/大小/MIME 与 parsed_object_key | 文件事实和原件/解析引用绑定具体版本；StoredDocumentVersion 承载私有对象引用，公开模型无原始对象 Key/URL |
| IngestionJob.idempotency_key 含 stage | Job Key 绑定版本、pipeline、job_type、terminal_stage，跨阶段/重试不变；独立 Stage Key 绑定版本、pipeline、stage |
| IndexVersion VALIDATING 与验证通过混用 | 增加 READY 表达已通过验证、尚未在线；ACTIVE 表示已确认发布，ROLLED_BACK 表示可保留回滚的历史版本 |

固定版本与 UTC 校验抽到 [共享契约内核](../../backend/app/core/contracts.py)，IAM 的既有导出保留；既有 IAM/Policy Schema 与真实 OpenAPI 制品保持一致。公共知识类型按 Schema Catalog 的 knowledge 分组生成；存储引用、文档 ACL、Manifest、实际 alias、完整验证事实和发布计划只生成内部 Schema。

## 主要契约

| 模型 | 字段与约束 |
|---|---|
| KnowledgeBase | id、name、description、status、embedding、active_index_version_id、created_by 和时间；状态 ACTIVE/DISABLED/DELETING/DELETED，删除完成才有 deleted_at |
| EmbeddingBinding | embedding_model_id、config_version、dimensions；三个字段固定向量空间，不从 POC 合成维度或候选模型推断默认值 |
| Document | id、kb_id、title、source_type、current_version、生命周期、acl_policy_id、创建主体及时间；新版本失败不改变旧版发布事实 |
| DocumentVersion / DocumentVersionRef | 版本实体 ID、document_id、kb_id、数值版本；MIME/大小/Hash、pipeline、Parser 与 Chunking 绑定、版本处理状态及时间 |
| StoredObjectRef / StoredDocumentVersion | 私有 bucket/object_key、内容 SHA-256 和正大小；不接受 URL；原件摘要/大小须匹配版本，PARSED 及后续状态须有解析产物引用 |
| IngestionJob | 固定版本引用、任务类型、pipeline、terminal_stage、执行状态/stage、稳定 Key、可信 requester_subject_id、trace_id、重试预算/进度、安全错误与时间 |
| IngestionEvent | job_id、单调 sequence_no、stage、event_type、attempt、安全进度/错误、occurred_at；失败/超时/重试必须有错误，重试错误必须明确可重试，PROGRESS 必须有进度，正常进度/成功不携带错误 |
| IndexVersion / StoredIndexVersion | KB、数值版本、状态、Embedding/Chunking/Pipeline、Manifest/验证引用与时间；私有物理名/alias 和完整报告放在 StoredIndexVersion |
| IndexManifest | 一个 IndexVersion 的文档版本清单；同 KB、每个逻辑文档最多一个版本，规范化摘要绑定成员和索引 ID |
| IndexValidationReport | 对应索引 ID、Manifest/配置摘要、预期/实际文档与 Chunk 数、Mapping/ACL/检索/质量检查、verdict 和检查时间；PASSED 不允许未知或失败检查 |
| IndexAlias / PublicationSnapshot / PublicationPlan | 当前逻辑/物理指针、目标/原版本及文档事实、原 CAS 期望、明确操作/Key、向量绑定与 alias 变更意图 |
| IndexPublication | 真实执行层确认后的发布/回滚记录；计划构造不能生成已经生效的历史事实 |

所有新对象采用独立字符串 schema_version="1.0"；标识为 UUID，数值版本从 1 起，时间有时区并归一 UTC。当前文件类型按已确认的 Markdown、DOCX、PDF 限定，MIME 字段不证明文件头、内容、安全扫描或 Parser 质量已验收。未知版本/字段、错误 Hash、空文件、时间倒序和不一致引用拒绝。

独立 JSON Schema 表达字段、类型与枚举；时间先后、错误/状态关系、摘要绑定等跨字段不变量由 Pydantic 校验器和应用规则执行，不能只凭 JSON Schema 通过认定整个契约有效。未来 HTTP 端点仍须明确映射为公开 DTO，不能直接序列化内部模型。

## 版本与任务状态

[入库生命周期模块](../../backend/app/modules/ingestion/application/lifecycle.py) 实现已定义版本迁移和 Job 的排队/运行/终态/重试规则。UPLOADED→PARSING→PARSED→CHUNKING→EMBEDDING→INDEXING→INDEXED→PUBLISHED 表达单个版本进度；处理失败进入 FAILED，完整重试回到 PARSING，清除旧 Parser/Chunking 事实和解析产物引用，重新解析后才能进入 PARSED。已发布版本不能回到处理态，新配置/内容创建新版本。任意可处理版本可进入删除，DELETING→DELETED 的持久化仍要求实际清理完成。

Job 的 SUCCEEDED 只表示其声明 terminal_stage 完成，例如完成 VALIDATING 不代表已经发布。时间不倒退，运行阶段不向后移动，重试只针对明确 retryable 的 FAILED 任务，保持 ID、版本、Key、主体和总预算；达到上限、取消、超时或未知外部效果不会自动重放。per-stage 去重、Event sequence 唯一性、租约/fencing、恢复检查点、实际持久化与消息确认由 Worker/数据库实现验收。

QUEUED→RUNNING→SUCCEEDED/FAILED/CANCELLED/TIMED_OUT，QUEUED 可直接取消；RUNNING 内阶段只向前。RUNNING/SUCCEEDED/FAILED/TIMED_OUT 必须保存首次 started_at，排队取消可无开始时间；所有终态必须有 finished_at。仅允许明确可重试且预算未耗尽的 FAILED→QUEUED，保留首次开始时间。事件类型为 STARTED、PROGRESS、STAGE_SUCCEEDED、FAILED、RETRY_SCHEDULED、SUCCEEDED、CANCELLED、TIMED_OUT；单条事件校验不证明跨事件顺序和数据库唯一性。

## 发布、回滚与当前读取

[发布规则](../../backend/app/modules/search/application/publication.py) 先检查当前 kb.manage，再核对 KB 状态、请求目标、CAS 期望、当前 IndexVersion 和真实 alias 观察值。发布目标必须 READY、验证报告与版本/Manifest/配置绑定，且与 KB 当前期望 Embedding 一致；清单成员必须属于同 KB、未删除、已 INDEXED/PUBLISHED，并使用匹配的 pipeline/Chunking。缺失成员、重复 ID、旧/错报告、未知质量、错指针/配置均拒绝。

回滚目标必须是曾发布、未清理、保留通过验证事实的 ROLLED_BACK 版本，清单成员仍须具有 PUBLISHED 历史。计划的向量绑定取自回滚目标，查询必须切换到该版本的配置，不能继续使用 KB 新配置生成向量。[构建状态函数](../../backend/app/modules/search/application/lifecycle.py) 仅允许 BUILDING→VALIDATING→READY 或失败；构建就绪不能被推断为已经执行发布。已发布索引只能保留 ACTIVE/ROLLED_BACK/RETIRED 生命周期，不能回到构建态；物理索引名不能等于 alias，目标版本不能复用当前物理索引。发布证据及在线读取的资源事实不能来自当前服务端时间之后。

实际执行确认后才允许 READY→ACTIVE、原 ACTIVE→ROLLED_BACK；回滚确认后目标 ROLLED_BACK→ACTIVE，原在线版本成为历史。历史清理后为 RETIRED，不能再次发布/回滚；本轮只实现构建规则与发布前提，未实现这些跨服务状态更新。

PublicationPlan 仅返回待执行的原 Key/CAS/alias/绑定意图，不修改数据库、ES 或输入对象。P3 执行层仍须验证每次实际发布、原 Key 同输入去重、条件更新、ES 原子 alias、失败后旧版可用及不确定结果对账，不能将多服务操作描述为单个数据库原子事务。

[在线文档读取规则](../../backend/app/modules/documents/application/access.py) 要求当前身份/KB 权限、KB 与逻辑 Document 有效、指定版本 PUBLISHED、活动索引/alias/Manifest 一致且包含该版本、pipeline/Chunking 对齐，以及当前 DocumentAccessPolicy。文档 ACL 只收紧 KB 权限：明确 None 表示继承，空主体集合表示拒绝所有，缺失或错误 Policy 引用/版本不能默认为继承。最新版本处理失败时，只要旧已发布版本仍在活动 Manifest 内即可读取；删除、撤权或移出 Manifest 后拒绝。

对象下载、Parent Context、引用和 Worker 恢复须各自重新使用当前事实。该纯读取规则不替代实际 Retriever/ES 查询中的强制范围和版本检查；正式衔接在 Retriever 契约与后续集成验证。

## 错误与执行责任

| 接口/场景 | 当前失败语义 |
|---|---|
| 字段、状态、时间与绑定不满足契约 | Pydantic ValidationError；错误摘要不包含原始输入，公开入口不得透传原始错误详情 |
| 非法版本/任务/索引构建迁移，预算耗尽或非安全重试 | ValueError；不改写输入，也不执行外部操作 |
| 当前身份/KB 管理权限不足 | PermissionError；拒绝准备发布 |
| CAS、alias、成员、配置与验证证据不一致 | PublicationRefusedError；不能将此拒绝当作已发布或可盲目重试的结果 |
| 在线资源、当前 ACL、索引/Manifest 不一致或未授权 | PermissionError；不返回可读版本引用 |

HTTP 和 Worker 的公开错误代码/消息由后续正式入口显式映射，当前没有新增业务路由或外部异常暴露路径。真实发布执行者负责原 Key 去重与结果回查，真实读取者负责当前事实加载、事务一致性和受控内容 IO。
