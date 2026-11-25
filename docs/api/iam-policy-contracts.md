# V1.0 身份与授权契约

日期：2026-11-25。P0-04-02 交付平台字段、显式身份关联、纯授权规则与 Schema；P1-03/04/05 已增加持久化、本地平台会话、固定角色矩阵与受保护 HTTP 接入。部署范围保持 [ADR-0013](../adr/0013-single-enterprise-deployment-scope.md) 的单企业模式。

## 身份调查与兼容

源码此前只有健康检查、公共 HTTP 契约与基础设施/Search Adapter，没有 IAM 表模型、迁移或身份路由。对本项目开发 PostgreSQL 的只读表盘点未发现业务基础表；本结论仅针对本地开发数据库。

V1.0 数据库详设使用 admin_users/employees，完整实施计划 P1-03 使用 users/identities。[IAM 契约](../../backend/app/modules/iam/domain/contracts.py) 以 User 表达稳定的平台逻辑主体，以 SubjectBinding 显式关联既有管理员/员工主体。P1-03 已核对实际消费者和本地开发库：没有来源档案表、业务 FK 或待迁移用户；新增 users/identities/subject_bindings 和权限/审计基础表，没有 UUID 回填或表重命名。精确身份唯一约束、来源关联和 FK、删除及回退策略见 [P1-03 实施记录](../plan/V1.0-MVP/implementation/P1-03.md)。此结论不覆盖未经盘点的外部数据库。

| 输入来源 | 唯一选择语义 | 处理规则 |
|---|---|---|
| 经供应商验证的外部身份 | provider_key + 精确 issuer + 精确 subject | 唯一有效 ExternalIdentity 指向 User；不修改大小写、补尾斜线、按 email/显示名猜关联 |
| 既有 admin_users | ADMIN_USER + 原 principal_id | 仅经 SubjectBinding 查平台 user_id；不直接复用原 UUID 作为平台主体 |
| 既有 employees | EMPLOYEE + 原 principal_id | 同上；与 ADMIN_USER 使用相同 UUID 值时仍分别查关联 |
| Role / Group | 明确类型与 ID | 角色/组 ID 保持其资源类型，成员关系从当前可信事实读取 |

[身份解析模块](../../backend/app/modules/iam/application/identity_resolution.py) 提供 resolve_external_identity 与 resolve_legacy_subject，接受可信服务端加载的记录。它只做关联和状态检查；签名、issuer/audience、state/nonce、Token/会话与 Provider 校验由 P1 登录模块先完成。没有记录、重复关联、缺失/重复 User、停用身份或非 ACTIVE 用户均返回稳定 IdentityResolutionCode，不创建用户或会话。错误不包含原始 issuer、subject 或个人信息。

## 公共模型

所有 IAM/Policy 对象使用字符串 schema_version="1.0"，当前读者拒绝其他版本和未知字段；此版本独立于产品版本、Policy 事实版本和数据库 revision。P1-03 已为身份、角色及关系落实数据库唯一/FK 约束；DTO 校验不代替事务和真实数据库验证。

| 模型 | 必需业务字段与限制 |
|---|---|
| User | id、display_name、status、created_at、updated_at；状态为 ACTIVE/DISABLED/LOCKED/PENDING_DEPARTURE/DEPARTED，仅 ACTIVE 可用；时间有时区并归一 UTC，更新不得早于创建 |
| Role | id、code、name、is_system、protected；三个固定代码 SUPER_ADMIN/KB_ADMIN/AUDIT_READONLY 必须为受保护系统角色，自定义角色不能占用这些代码或声明为系统角色 |
| Permission | id、code、resource、action、description；code 精确等于 resource.action，采用小写标识；角色集合与资源 ACL 分别计算 |
| UserRole / RolePermission | user_id + role_id / role_id + permission_id；关系 ID 指向规范实体，P1-03 已落实 FK/复合主键约束 |
| ResourceGrant | id、kb_id、principal_type、principal_id、permission；permission 为 READ/MANAGE，MANAGE 包含 READ，READ 不包含 MANAGE |

ResourceGrant 保留 ADMIN_USER/EMPLOYEE/ROLE/GROUP 来源类型，并增加 USER 表达平台 User.id。旧来源类型的 principal_id 保持原语义，授权时经明确映射读取；未建立关联时拒绝，不因 UUID 值碰巧等于 User.id 而授权。角色和组成员身份不授予未明确关联的 KB。

公共模型通过 [Schema Catalog](schema-catalog.json) 登记，在 [IAM 生成类型](../../frontend/packages/api-client/src/generated/iam.ts) 和公共 api-client 导出。User 不含外部 issuer/subject、密码、Token 或 sourceId。身份键、关联事实及授权快照仅生成内部 Schema，不进入前端类型或实际应用的 OpenAPI。

## 内部上下文与授权事实

| 内部模型 | 字段与前提 |
|---|---|
| IdentityKey / ExternalIdentity | 已验证 Provider 的精确选择键，身份 id、规范 user_id、ACTIVE/DISABLED 状态；原始键为受限信息，repr 与错误不回显 |
| LegacyPrincipalKey / SubjectBinding | 来源类型、原 principal_id 与规范 user_id，要求唯一显式关联 |
| AccessContext | subject_id、identity_id、actor_ref、environment、purpose、policy_version、issued_at、expires_at；可信服务端构造，没有角色/权限/KB Grant 声明字段 |
| AuthorizationRequest | 服务端从当前用例选择 permission_code 和 purpose；kb.read/kb.manage 必须有 kb_id，其他操作不接受 KB 来替代操作授权 |
| AuthorizationSnapshot | 当前 User、ExternalIdentity、角色/组 ID、操作权限、ResourceGrant、SubjectBinding、环境/目的/Policy 版本、观察和有效时间；身份必须属于该 User，关联和 Grant 不得歧义/重复 |
| PolicyDecision | ALLOW/DENY、稳定 reason_code、subject_id、permission_code、kb_id、policy_version、decided_at；允许结果必须有主体与 ALLOWED 原因 |

environment 当前支持 development/test/production，purpose 当前支持 admin/chat。此 IAM 接口的 Chat 用途只允许 KB read；会话、消息、文档及引用的资源规则在对应主线契约实现。没有 Tenant 或后续版本 Organization/Workspace 字段。

actor_ref 为以服务端独立密钥生成的 HMAC 伪名引用；[生成函数](../../backend/app/modules/policy/application/authorization.py) 要求至少 32 bytes 的已解析服务端密钥，不提供默认值。它用于关联，不能代替 subject_id/identity_id 或证明身份；密钥解析、托管与轮换由实际身份/安全模块装配。

## 授权模块接口

[authorize](../../backend/app/modules/policy/application/authorization.py) 使用 AuthorizationRequest、可空 AccessContext、独立的当前 AuthorizationSnapshot 及有时区的服务端 now。输入记录必须由可信认证/Policy 模块从当前状态加载，不能将客户端、Prompt、JWT 角色声明或 MQ 消息头复制成有效快照。

按顺序拒绝：缺少上下文、主体/身份不匹配、用户/身份停用、上下文或快照过期/未生效、环境/目的/伪名/Policy 版本不一致、操作权限缺失、KB Grant 或当前成员关系缺失。KB 匹配范围只来自明确 Grant 与当前用户/角色/组/来源关联，调用者的 kb_id 仅表示选择意图。

PolicyDecision 绑定当前检查对象，不能当作可重放 Token 或替代其他操作、对象下载、引用扩展、Worker 恢复时的重新授权。有效期校验不证明缓存仍代表最新权限；P1 生产者必须在每次操作重新加载一致的当前身份、权限、成员与 ACL，失败时拒绝。原 [Search Adapter](../../backend/app/adapters/elasticsearch.py) 仍使用自己的内部 AuthorizedSearchScope，Retriever/文档关系就绪后再验证 Policy→Search 的真实衔接。

P1-05 的 [执行与迁移记录](../plan/V1.0-MVP/implementation/P1-05.md) 固定 23 个操作码和三个系统角色的矩阵。PolicyEnforcer 从当前数据库事实构造上下文，KB 内容必须同时具备操作能力与目的匹配的显式 Grant；后台角色不授予 Chat 内容。只有不可委派的 acl.manage 可配置第一份 ACL，ACL 明细查询另要求目标 KB 可读。缺组成员事实时 GROUP 持久化/API 拒绝，不能猜测成员关系。自定义角色只接受只读集合；统一授权仍过滤意外的管理权限关系。

真实企业 OIDC、KB/文档实体及 Policy→Retriever 集成仍按对应主线验收；不能用本地会话和权限范围 ID 测试替代这些交付。完整 P0-04/M0 及 P1/M1 不因上述基础实现自动关闭。
