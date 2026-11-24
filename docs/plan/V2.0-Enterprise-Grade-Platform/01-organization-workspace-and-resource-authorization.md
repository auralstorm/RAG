# 01｜企业内部组织、Workspace 与资源授权

> 版本：V2.0。所有版本采用单一企业内部部署，范围见 [ADR-0013](../../adr/0013-single-enterprise-deployment-scope.md)。公共语义见 [统一契约第 2/11 节](../../architecture/统一契约与跨版本演进规则.md)，表/API 见 [07](07-database-api-and-contract-design.md)。

## 1. 组织与协作范围

Organization 表达本企业部门、团队及层级关系，Workspace 表达协作成员、资源和环境范围。Workspace 可关联本企业 Organization；两者均复用现有 Identity/Policy，不引入企业客户目录或新的独立客户管理服务。

用户/角色/KB ACL 和资源 Owner 是既有授权依据。Workspace 成员可查看哪些资源仍需当前 Policy 和资源 ACL 决定，新增默认 Workspace 不给全部员工开放历史 KB、对话、Agent、Workflow、凭据、审批或费用。

资源不必统一强制带 workspace_id：已归属 Owner/KB/父对象的历史资源按原授权继续服务。仅当前协作需求需要的资源增加明确关联；部署实例 namespace 用于环境与存储命名，不能作为访问凭证。

## 2. 可信身份与授权上下文

认证层验证 issuer/sub/sourceId、用户映射、会话状态和当前成员关系。复用已有 AccessContext，适用字段见统一契约第 11.1 节；组织/Workspace 请求参数只是待验证的目标范围。

切换 Workspace 时服务端校验当前成员、角色、资源及环境授权。成员/角色撤销影响后续读取、检索、执行及恢复，不依赖旧 Token 或 UI 刷新；缺少必需身份与资源授权时拒绝。

Worker、Webhook、审批回调与 Timer 从持久 Job/Instance/Trigger 的 Owner 和资源关系解析范围，校验消息引用及当前 Policy。消息或外部 payload 不能授予权限，服务身份仅拥有执行该任务所需的能力。

## 3. 数据与派生资源权限

| 边界 | 必须执行的规则 |
|---|---|
| PostgreSQL | Owner/成员/ACL 由可信服务端查询；子对象通过父对象授权，创建/更新关系不得绑定未授权资源 |
| Elasticsearch | 检索强制当前 KB/资源 ACL；索引/alias、Parent Context 和引用查看保持原资源授权 |
| Redis/缓存 | 部署 namespace、有效授权摘要或主体、配置版本进入 Key；撤权后失效并重新验证 |
| 对象/附件 | Prefix 区分部署环境，签名下载前验证当前资源；对象 Key 不是公开访问凭证 |
| 队列/任务 | 校验持久 Owner、任务版本、当前权限和 Deadline；重放不提升权限 |
| Tool/Connector/模型 | 受控 Allowlist、环境与凭据引用；服务账号技术能力不替代用户/业务授权 |
| Trace/Audit/评测/账目 | 摘要、报告、导出按资源与专门权限查询；普通用户无全平台数据访问权 |
| 备份/恢复 | 恢复后先应用当前身份撤权、资源 ACL、删除/保留及审批规则，再开放访问 |

在线问答、入库、评测、Workflow 与恢复执行池按负载分开，系统/部门/用户/模型额度防止内部任务争用；容量和安全各自验证，预算不得绕过资源权限。

## 4. 兼容与管理

盘点实际 Organization/Workspace/成员能力，优先复用，补齐当前需要的资源授权缺口。新增组织/协作关联按普通 Expand、旧消费者兼容、数量/Hash/引用与授权回归逐步实施，不要求给全部历史资源补齐新的统一归属列。

稳定 UUID、Agent/Workflow 快照、Run 客户端 Key 和外部 operation_key 保持原值。API、SSE、回调和内部任务沿用同一授权服务；组织层级与成员变更不能改写运行历史或重建外部操作 Key。

组织/Workspace 管理权限与内容读取、成员绑定、发布/运行/预算及凭据权限分开。员工离职、成员撤销或资源停用阻止新的未授权访问，保留已发生业务效果与未知账目，由具备当前授权的人员核对和处置，详见 [04](04-enterprise-security-compliance-and-data-lifecycle.md)。

## 5. 验收

使用本企业多个用户、角色、KB 和 Workspace，覆盖读写、关系绑定、检索/来源、缓存/对象、任务/Tool、审批、报告/费用与恢复的正负向授权。跨部门访问只有显式授予后才通过，取消授权后后续调用失败。

验证历史无 Workspace 的资源保持原 ACL，新增组织/成员不扩大权限，旧 Key/快照不变，缺上下文、伪造身份/消息、未授权资源 ID 均拒绝。企业内权限验证与高可用/预算/灾备分别提供证据，不以关闭 UI 按钮代替服务端授权验收。
