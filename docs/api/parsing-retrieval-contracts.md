# V1.0 解析、切片与 Retriever 契约

日期：2026-11-24。对应 P0-04-04，依赖已交付的身份/Policy 与知识版本契约。交付平台模型、来源与权限纯规则、Parser/Retriever 接口和可执行 Schema；Docling/MinerU、Tokenizer、Embedding、数据库/对象存储读取与正式 Search Adapter 衔接按 P3/P4 集成，实际 Docling 验证仍留到 P3-01。

## 现有消费者与兼容

此前没有 ParsedDocument、Chunk 或正式 RetrievalRequest/Result 实现。已有 [HybridSearchAdapter](../../backend/app/adapters/elasticsearch.py) 是独立 Search POC 的内部接口，SearchQuery/AuthorizedSearchScope/SearchCandidate 和 ES Chunk 投影已有消费者；本轮保持其字段与行为，不把合成权限范围冒充正式 Retriever 授权。完整业务路由未实现，实际 OpenAPI 继续只包含健康检查及公共错误组件。

| 原详设草案 | 本轮规范与后续适配 |
|---|---|
| ParsedDocument.document_id / version / parser | 复用 DocumentVersionRef 的完整实体/数值版本关系；parser_name 对齐 DocumentVersion，旧 version/parser 仅在实际 Adapter 映射 |
| pages.page_no 与 bbox/source_location 任意字典 | 页码仅用于 PDF；SourceLocation 为明确文件格式的联合类型，坐标与字符偏移分开 |
| metadata / warnings 任意字典或原始字符串 | ParsedDocumentMetadata、ParsingWarning、ChunkMetadata 采用明确字段；SDK 原始对象/异常与未登记扩展字段拒绝进入平台契约 |
| Chunk.page_no、char_start/char_end、heading_path | 来源分别在 source.spans[*].location 与解析块切片范围中；标题路径在 metadata，单一 page_no 不能表达跨页 Chunk |
| RetrieverRequest / RetrieverResult | 规范名称沿用 RAG 详设的 RetrievalRequest / RetrievalResult；SearchQuery 等 POC 类型保持为 Adapter 内部协议 |
| filters / score_components / source 任意字典 | RetrievalFilters、ScoreComponents、ChunkSource 显式定义；不接收 DSL、acl_snapshot 或可自授的角色/资源上下文 |

所有新实体/值对象从字符串 schema_version="1.0" 起维护，未知版本/字段拒绝。无业务 DDL、数据迁移、Parser/Worker 安装或外部服务写入。JSON Schema 表达字段与枚举，跨字段摘要、顺序和关系由实际 Pydantic 校验与应用规则执行。

## 原文定位与解析结构

[解析模型](../../backend/app/modules/parsing/domain/contracts.py) 定义 ParserInput、ParsedDocument、ParsedPage、ParsedBlock、ParsedTable、ParsedDocumentMetadata 和 ParsingWarning。ParserInput 仅在服务端包含已解析的私有 StoredObjectRef；调用用例拥有当前授权、版本与 IO，Parser Adapter 负责有界执行、格式检测、输出映射及安全错误分类。[输出校验](../../backend/app/modules/parsing/application/validation.py) 检查具体版本、KB、MIME 与原件 SHA-256；字段相符不证明实际文件解析质量。

| SourceLocation.kind | 位置规则 |
|---|---|
| pdf | 原始 PDF 一基页码；可空 bbox，存在时为显示方向、左上角原点的 [0,1] 坐标，面积为正且有限 |
| markdown | 原始解码 Markdown 中的 Unicode 码点半开范围 [char_start,char_end)，不使用 UTF-8 字节或浏览器 UTF-16 下标 |
| docx | 原始正文中按段落/表格混合顺序计数的零基 element_index 与 element_type；不伪造实际分页 |

PDF 页容器必须保留完整连续页码，包括没有可用块的空页；Markdown/DOCX 使用一个 page_no=null 的容器。块 ID 在版本内唯一，数组保留解析得到的阅读顺序；块和告警位置必须匹配格式及所在 PDF 页。标题/段落/表格/列表/图注有固定枚举，表格块必须包含矩形规范化单元格，其他块不能携带表格。

本轮表格模型保存矩形单元格文本；复杂合并单元格、图像/OCR、阅读顺序和定位准确性须由 P3-01 的真实样本验证。Adapter 无法无损表达的结构需产生稳定告警代码，例如 TABLE_STRUCTURE_LOSS，不能静默声称完整保留。原始文本范围的真实性与源文件长度由真实 Parser 校验；本轮不以合成输入代替此验证。

## Chunk 与父子来源

[Chunk 模型](../../backend/app/modules/chunking/domain/contracts.py) 复用完整版本引用，固定 id、零基 chunk_index、role、parent_chunk_id、content/content_hash、token_count/tokenizer_version、chunking_config_version、source/metadata 与 UTC created_at。内容 Hash 必须匹配 UTF-8 文本；角色为 STANDALONE/PARENT/CHILD，只有 CHILD 必须引用不同的父 ID。完整原文与 Chunk 仅生成内部 Schema，公开结果只能携带已授权的 RetrievedChunk。

ChunkSourceSpan 的 char_start/char_end 是 ParsedBlock.text 中的 Unicode 码点半开切片，与 location 的原始文件位置分别维护。[Chunk 集合校验](../../backend/app/modules/chunking/application/validation.py) 验证同一版本、唯一 ID/索引和同一 Chunking/Tokenizer 配置；块引用、位置、范围与标题路径须匹配 ParsedDocument。文本按来源顺序取切片、以两个换行连接，不重复或逆序复制同块范围；语义改写不能作为原文证据。

CHILD 的父必须是同一集合内的 PARENT，所有子来源范围都在父来源范围内；不凭文本相似推导关系。空解析页可产生空 Chunk 集合。token_count 只是带版本的受验证元数据，实际计数、切片策略、Overlap/预算与质量仍由正式 Tokenizer/Chunker 集成验收。本轮提供校验器，没有生成业务切片。

## Retriever 输入与当前权限

[Retriever 模型](../../backend/app/modules/rag/domain/contracts.py) 保留 query、kb_ids、filters、服务端 access_context、top_k、可空 config_version、trace_id，以及 chunks/diagnostics。RetrievalSelection 是客户端业务选择，不含 AccessContext/Trace；RetrievalRequest 仅在可信服务端构造。query 不为空且最多 4000 字符，KB 选择 1–100 个且唯一，top_k 为 1–100 的整数，再受当前服务端配置 max_top_k 限制；这些是接口保护上限，不是业务容量/SLO 冻结值。

filters 仅允许 document_ids/source_types，来源类型沿用 UPLOAD/CONNECTOR；空业务筛选仍执行强制授权范围。显式不存在或未授权 KB/Document 选择拒绝，不退化为全库。config_version=null 表示由服务端解析当前配置，执行范围固定解析后的版本；显式未知版本或超过当前上限拒绝。Trace 为服务端非零 32 位十六进制关联 ID，不提供权限。

[范围准备规则](../../backend/app/modules/rag/application/retrieval.py) 对所有请求 KB 执行当前 kb.read Policy，再通过既有 require_published_document 校验逻辑文档、当前版本、活动 index/alias/Manifest 与当前文档 ACL；失败文档从可检索集合排除。显式 Document 筛选若含不可读对象则拒绝请求。得到的 AuthorizedRetrievalScope 绑定完整可读版本清单及当前 index/Embedding/Chunking/Pipeline，不使用 KB 的未来期望 Embedding 替代活动索引向量空间；截止时间不超过身份上下文和当次授权事实的有效期。

空授权版本集合必须跳过搜索 IO；不可将空列表解释成不筛选。RetrievalFacts 由可信服务端重新加载当前事实与已解析配置，不能来自客户端或搜索响应；本轮纯规则尚未接入实际 Repository 或网络。正式 Retriever 实现仍须按每个 KB 的活动索引和独立向量空间执行查询，落实强制版本/ACL 条件、候选上限、超时及取消。

## 结果、引用与再次校验

RetrievedChunk 携带 chunk_id、完整版本引用、index_version_id、授权内容、有限 score、ScoreComponents、ChunkSource 与 ChunkMetadata。ScoreComponents 保留可空 Dense/BM25 排名、RRF/重排分数；RRF 分数存在时至少有一个来源排名，分数不表示回答正确率。RetrievalDiagnostics 仅提供当次 Trace、固定配置版本、返回数量与 elapsed_ms，不公开物理索引、对象 Key、主体 Grant 或被拒文档数量。

validate_retrieval_result 使用新加载的事实重新准备权限范围，核对原 Scope 有效期、Trace/config 与 top_k。先核对本次检索使用的活动索引绑定，包括候选为空的情况。候选必须同时属于原始与当前可读版本，并与可信当前 Chunk 的版本、内容、来源/元数据和 Chunking 配置一致。缺少权威 Chunk 证据、候选伪造、撤权、删除或索引切换均拒绝整个结果。生产实现负责从可信已发布产物读取权威 Chunk。

来源引用和 Parent Context 扩展继续复用当前资源校验。Conversation/Message/Citation 的消息级编号、答案引用校验与对象下载在后续分项交付，本轮只冻结片段级来源证据。异步 Retriever Protocol 仅规定调用边界，没有提供联网的完整 Retriever 实现或绕过 Gateway 的 Embedding 调用。

## 错误与制品

字段/版本/结构错误为 ValidationError，关系/配置/顺序冲突为 ValueError，当前身份/资源不足及非法候选为 PermissionError；错误摘要不含原始输入/内容。HTTP/Worker 在正式入口显式映射稳定代码，Parser/Search 技术错误按 Adapter 分类，不透传 SDK 原始诊断。

Schema Catalog 新增公共 retrieval 分组：客户端选择/筛选、授权返回与诊断、片段来源/元数据/评分；ParsedDocument、原始 Chunk、ParserInput、RetrievalRequest/授权事实/范围只生成内部 Schema。`make contracts` 从源码生成，`make contracts-check` 核对一致性；生成器同时转换标准 $ref 与 discriminator.mapping 引用，公共 TypeScript 可以保留三种来源位置的判别联合。现有 OpenAPI、IAM/knowledge 制品与 POC Adapter 消费者继续兼容。
