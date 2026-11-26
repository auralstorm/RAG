# V1.0 Trace 与 AuditEvent 契约

## Trace 技术诊断

[Trace](schemas/observability/trace.json) 记录 32 位小写非零十六进制 Trace ID、服务端 Request ID、RAG 配置版本、索引版本以及 [Span](schemas/observability/trace-span.json) 列表。每条 Trace 有一个 `rag.answer` 根。阶段 Span 使用 16 位小写非零十六进制 ID，父子关系必须在同一棵树内，时间范围必须包含于父级。UTC 起止时间用于计算耗时。`RUNNING` 的结束时间为空，`FAILED` 和 `REFUSED` 必须提供稳定错误分类。

Span 提供显式诊断字段，包括候选数、文档版本、Prompt 版本、模型及其配置版本和结构化用量。普通视图只承载上述技术字段。历史会话正文、原始提问、Prompt、供应商返回文本、用户标识及身份关联留在各自的受控存储边界。受控内容预览及文档访问授权按 P5 验收。

[TraceIdentityLink](schemas/internal/trace-identity-link.json) 为独立的私有记录，包含 Trace ID、Request ID、受保护身份引用与失效时间。实际查询和身份溯源应由服务端绑定这两个关联 ID。HTTP 的客户端父上下文本身只提供链路关联信息。P5 实现身份解析、失效与权限规则，包括超级管理员、原因、二次确认和可持久化的审计结果。

## AuditEvent 操作审计

[AuditEvent](schemas/observability/audit-event.json) 供授权管理员与审计员查询。事件记录 ID、UTC 时间、动作、风险、结果、请求/链路关联、操作者及角色快照、来源 IP 和动作目标。动作枚举覆盖 V1.0 的登录、角色/权限、供应商/模型、知识库、RAG 配置发布、身份溯源及用户生命周期。动作前缀用于按模块归类。

前后摘要使用显式字段，覆盖启用状态、用户状态、用户获准的 Chat/Admin 应用入口、角色/权限/配置 ID 及凭据是否存在。用户建号只记录状态与应用入口，不记录用户名、密码或密码哈希。失败和拒绝事件只记录动作与可用的变更前摘要。身份溯源成功要求高危等级、已知操作者、目标 Trace ID 及受保护原因记录。查询请求的 Trace ID 与被查看的 Trace ID 分别记录。原因引用只出现在 [StoredAuditEvent](schemas/internal/stored-audit-event.json)。

P1-05 增加可选的成对字段 resource_grant/resource_purpose，分别保存明确主体/KB/READ 或 MANAGE 的 Grant 与 admin/chat 用途；旧摘要缺字段仍有效。平台账号建号使用 application_access 记录入口授权，ACL 建立、修改与删除记录受影响单条 Grant 的前后摘要，角色权限编辑记录权限 ID 的前后集合，均与业务变更同事务写入，不保存任意请求正文。生成 Schema/前端类型同步更新，查询服务仍由 P1-06 交付。

全部制品采用 `schema_version=1.0`。原 `rag_traces`、`audit_logs` 表草案的关联 ID 和身份引用按上述契约映射。[P1-06](../plan/V1.0-MVP/implementation/P1-06.md) 已统一追加 Writer，补齐新登录的当前角色/IP 和权限变更的 IP/失败目标，提供 `GET /api/v1/admin/audit-logs` 的当前 audit.read 授权、精确筛选和分页。AuditLogView 增加由 action 派生的 module；总数和页内数据在同一 SQL 快照读取。私有原因不进入响应，畸形历史摘要拒绝而不透传。

登录/权限变更与审计失败关闭已由真实 PostgreSQL 验证；普通 API 没有审计增改删，数据库 UPDATE/DELETE/TRUNCATE 继续受保护。无新 migration，旧事件缺失的角色/IP 不回填；审计保留与后续资源操作/P5 高危溯源继续按真实用例验收。

登录及 RBAC 写操作在 Origin 或会话验证时提前拒绝，也通过同一 Writer 提交匿名 DENIED：保留服务端选定的动作、可用目标、直接连接 IP 与 Request/Trace ID，操作者和前后摘要为空、角色快照为空，不采信无效凭据中的身份。追加失败返回脱敏 503，不宣称拒绝已审计。DTO 校验、会话读取/续期/登出及未配置服务不在这项补漏的事件覆盖范围内；没有新增动作或 Schema 字段。
