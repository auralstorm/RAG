# V1.0 会话、消息与引用契约

## 公共与内部制品

| 制品 | 字段与语义 |
|---|---|
| [Conversation](schemas/chat/conversation.json) | 会话 ID、标题、UTC 创建与更新时间。 |
| [Message](schemas/chat/message.json) | 消息 ID、会话 ID、会话内正整数 sequence、角色、状态、UTC 创建时间，以及按角色与状态提供的正文、Trace ID 和引用。 |
| [Citation](schemas/chat/citation.json) | 消息内确定的 citation_id 与序号、完整知识文档版本、已检索 Chunk ID、标题、格式化原文定位、章节路径与最长 320 字符的片段摘录。 |
| [StoredConversation](schemas/internal/stored-conversation.json) | 公共视图及服务端保存的 User.id 归属与删除时间。 |
| [StoredMessage](schemas/internal/stored-message.json) | 消息及本次生成使用过的所有原文版本依赖，涵盖正文中没有标注的证据。 |

所有制品沿用 `schema_version=1.0`。`USER` 消息为带正文的 `COMPLETED`。`ASSISTANT` 消息要求非全零的 32 位小写十六进制 Trace ID。只有 `COMPLETED` 助手消息携带带引用的回答正文。`GENERATING`、`REFUSED`、`FAILED`、`CANCELLED` 均为无正文状态，其中 `GENERATING` 可进入四种终态，P4 的写入用例负责原子状态转换。系统指令由内部模型调用契约承载。

## 确认回答与读取历史

- 服务端将实际送入模型的检索片段按 Prompt 顺序编号。模型正文使用 `[[cite:1]]` 形式引用序号，允许重复使用同一个序号。缺失、越界或格式错误的标记拒绝确认回答。拒答时 API 可按 `REFUSED` 状态呈现固定提示。
- 完成回答时复用 Retriever 当前校验，核对原检索范围、关联 Trace、索引、完整文档版本及权威片段。引用标题读取服务端文档元数据，定位和摘录来自已验证 Chunk。摘录是该 Chunk 的文本前缀，定位集合描述整个 Chunk。引用 ID 按消息 ID 与证据序号确定。
- 读取会话要求当前 Chat 身份和匹配的规范平台 User.id。不存在、其他用户持有、已删除的会话使用相同的不可用结果。读取消息还要求其确实属于目标会话。
- 历史读取、引用详情和历史上下文复用均需重新确认消息涉及的全部原文版本仍在当前可访问的发布清单内。缺失、撤权、删除或发布版本替换时，整个回答正文与引用均不可交付。将来把先前回答送入模型时，P4 用例需保留这些回答的原文依赖，覆盖间接使用的证据。
- 纯规则通过 `LookupError` 表达资源不可用，通过 `PermissionError` 表达当前身份或证据不可用，通过 `ValueError` 表达无法确认的生成数据。P4 API 负责安全映射、关联与呈现，并对源文件访问执行当前授权。

原数据库草案的 `employee_id` 后续通过显式 `SubjectBinding` 映射规范 User.id。`source_snapshot` 的业务数据对应 Citation 的完整版本与格式化定位。PDF 页码保留在 PDF 定位中，Markdown 和 DOCX 采用各自的原文位置。下载链接由将来的受权来源接口按需生成。

数据库迁移、会话顺序与并发写入、删除清理、失效回答的呈现、SSE 协议与缓冲发布、反馈及来源访问按 P4 验收。
