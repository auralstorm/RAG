# RustFS 对象存储选型研究

- 核验日期：2026-11-24（Asia/Shanghai）。
- 任务范围：评估 RustFS 是否适合作为 V1.0 对象存储候选；未授权替换现有服务或改变技术基线。
- 状态：一手资料研究完成；RustFS 运行、性能、安全回归、迁移与恢复 POC 均未执行；选型决策待确认。
- 本项目入口：[POC-08 对象存储维护、安全与选型复核](../04-poc-acceptance-and-adr.md#11-poc-08-对象存储维护安全与选型复核)。

## 1. 建议

**建议把 RustFS 列为 POC-08 的优先候选，通过本项目必要的授权、S3、删除、恢复与升级检查后，再决定切换。现有证据尚不足以直接冻结生产基线。**

RustFS 已发布稳定版，服务端采用 Apache-2.0，官方资料及发布标签源码覆盖本项目所需的基础 S3 操作、预签名 URL、多段上传和生命周期。这些事实支持投入验证。[R1][R3][R4][R5] 但稳定版发布历史较短，安全公告涉及本项目依赖的授权与上传接口，兼容矩阵保留明确限制，升级和磁盘迁移也有边界。[R2][R5][R10][R13][R14] 仓库活跃和 Star 数不作为生产成熟度证明；Rust 内存安全也不能证明 IAM、签名或删除规则正确。

本项目既有旧 MinIO 的维护与安全问题仍按 POC-08 处理；RustFS 候选研究不会自动关闭该问题，也不代表旧版本已修复。业务仍按单企业内部部署与服务端资源 ACL 授权推进，无需采用 RustFS 宣传中的多租户或本项目后续版本能力。

## 2. 证据与验证边界

研究使用 `curl` 读取 RustFS 官方 GitHub API、官方文档站和官方仓库文件。源码核验固定在发布标签 `1.0.6`，Git tree API 返回提交 `de9009d882644effc2628e777650025c3d8e7c65`；`main` 和文档站仅作为动态资料对照。[R1][R6]

文中的证据分为三类：

| 类型 | 本次能证明的内容 | 本次不能证明的内容 |
|---|---|---|
| 官方声明 | Release 的稳定标记、README 功能表、支持政策、文档操作契约 | 长期生产稳定性、支持 SLA、宣传性能在本项目成立 |
| 发布源码/测试清单 | `1.0.6` 包含对应入口、授权检查、回归测试及兼容范围清单 | 当前官方二进制/镜像的实际执行结果、全部上游 CI 当前通过 |
| 本项目实测 | 本次没有运行 RustFS 或执行 POC | 项目 SDK、浏览器上传、ACL、故障恢复、规模、升级和迁移均待验证 |

本次未下载或启动 RustFS 镜像，未成功核验镜像实际 manifest/digest、签名、SBOM 漏洞扫描结果或运行内存，未更改现有容器、卷、依赖或配置。只读执行 `docker buildx imagetools inspect rustfs/rustfs:1.0.6` 时 registry 连接重置，不能由此判断 tag 不存在或已可拉取。所有动态来源均应在实际 POC 冻结版本时复核。

## 3. 发布、维护、许可证与安全

| 项目 | 已核验事实 | 选型含义 |
|---|---|---|
| 仓库维护 | 官方 API 的 `archived=false`、`disabled=false`，`pushed_at=2026-11-24T03:29:06Z`。[R1] | 相比已停止维护的旧社区服务端，有公开维护活动；不能由此推导维护期限或生产 SLA。 |
| 最新稳定版 | GitHub latest Release 为 `1.0.6`，`prerelease=false`，发布日期 `2026-11-15T23:26:57Z`。[R2] | 截至核验日称 RustFS 仍只有 alpha/beta 已不准确；POC 优先固定此版本及实际镜像 digest。 |
| 稳定/预发布历史 | `1.0.0` 于 `2026-09-16` 发布且 `prerelease=false`；读取最近 100 个公开 Release 并按发布时间排序，最新标记预发布为 `1.0.0-rc.6`（`2026-09-11`），此后可见 `1.0.1` 至 `1.0.6` 稳定发布。[R3] | 有稳定发行渠道，但当前 1.0 稳定发行历史约两个多月；不能把稳定标签等同于长期故障与恢复证据。该列表核验不覆盖未发布 tag、私有草稿或独立分发渠道。 |
| 许可证 | `1.0.6/LICENSE` 为 Apache License 2.0；仓库 API 也标记 `Apache-2.0`。[R1][R4] | 是许可宽松的开源服务端候选；实际交付仍核对镜像附带组件、NOTICE 与依赖许可证，不由项目比较表推导法律结论。 |
| 安全维护政策 | `1.0.6/SECURITY.md` 表示 Latest 获安全更新，`<1.0` 不支持；提供私人公告入口与 `security@rustfs.com`，声明 48 小时确认报告。[R7] | 未见此文件承诺历史稳定分支 LTS 或修复时限；需要持续升级能力。48 小时确认属于公开政策，不等同支持合同。 |
| 安全公告 | `security-advisories?per_page=100` 返回 43 条公开公告；包括服务账号、预签名上传、前缀删除和 Object Lock 问题。[R8] | 公开披露与修复是正面维护证据；公告数量既不能单独证明产品不安全，也不能证明最新版本安全。必须按具体受影响范围和发布源码回归。 |
| 发布制品 | `1.0.6` Release 列出 Linux x86_64/aarch64 的 GNU/musl 制品、macOS aarch64、Windows x86_64、SHA256SUMS/SHA512SUMS、SBOM 和 provenance JSON。[R2] | 有可复核供应链入口；本次仅核对 API 中制品元数据，未验证下载内容或 attestations。 |

与本项目直接相关的公开安全事实：

| 议题 | 官方公告及修复标记 | 本项目需要的回归 |
|---|---|---|
| 服务账号跨用户/root-parent 提权 | [GHSA-5354-r3w2-34m8](https://github.com/rustfs/rustfs/security/advisories/GHSA-5354-r3w2-34m8)（`CVE-2026-73284`）标记 `<1.0.0-beta.11` 受影响、`1.0.0-beta.11` 修复；[GHSA-566f-q62r-wcr8](https://github.com/rustfs/rustfs/security/advisories/GHSA-566f-q62r-wcr8)（`CVE-2026-45043`）记录 IAM 导入生成任意父身份账号的问题。 | 受限用户不能创建、导入、更新或枚举他人/root 的服务账号；派生凭据不能扩大父身份策略。 |
| 预签名上传注入未签名头、变成跨桶 CopyObject | [GHSA-g8w9-qw9q-fghr](https://github.com/rustfs/rustfs/security/advisories/GHSA-g8w9-qw9q-fghr) 与 [GHSA-xm99-m3gq-83g8](https://github.com/rustfs/rustfs/security/advisories/GHSA-xm99-m3gq-83g8) 均标记 `1.0.0` 修复；后一公告明确说明早期修复没有关闭实际攻击路径。 | URL 的方法、目标桶/键、有效期、签名头和元数据必须绑定；加 `x-amz-copy-source`、标签或 SSE 头不能扩大上传授权。 |
| 批量删除绕过前缀范围 | [GHSA-g7fq-6xjm-mxf4](https://github.com/rustfs/rustfs/security/advisories/GHSA-g7fq-6xjm-mxf4) 标记 `<=1.0.1` 受影响、`1.0.2` 修复；涉及版本桶的 `.`/`..` 键生成其他前缀删除标记。 | 限定前缀的批量删除不能影响其他前缀；覆盖未版本化、启用版本和暂停版本桶。 |
| 保留对象被强制删桶移除 | [GHSA-28w4-rp2p-636w](https://github.com/rustfs/rustfs/security/advisories/GHSA-28w4-rp2p-636w) 标记 `1.0.0` 受影响、`1.0.2` 修复。 | 若项目实际启用保留/锁定，覆盖删对象、删版本、强制删桶、生命周期和故障元数据读失败；未采用 WORM 时不提前引入该功能。 |
| 其他监听协议绕过桶策略 | [GHSA-rhg6-jrf2-29c4](https://github.com/rustfs/rustfs/security/advisories/GHSA-rhg6-jrf2-29c4) 标记 `<=1.0.1` 受影响、`1.0.2` 修复。[R8] | POC 核对实际启用的监听器与网络暴露；MVP 只启用所需接口，不能只回归 S3 路径便推导其他协议授权正确。 |

上述修复标记不意味着 `1.0.6` 仍有同一已知漏洞。`1.0.6` 的服务账号源码已存在父身份范围检查，认证源码存在未签名 `x-amz-*` 头拒绝逻辑，预签名负向测试覆盖过期、签名/键篡改及注入头。[R9][R11][R12] 本次没有运行这些测试，不能声称安全 POC 通过。

部分旧公告的版本字段不规范，例如 `All versions` 同时列出 `alpha.79` 修复，另有 `0.1.0`/`1.0.0` 格式混用。[R8] 因此不直接用简单字符串比较生成“1.0.6 无漏洞”的结论；实际准入需要公告正文、修复提交、固定制品和回归结果相互核对。

## 4. S3、IAM 与本项目需求匹配

`1.0.6` 兼容矩阵声明 broad S3 API compatibility，并明确**不承诺所有标准或供应商扩展行为完整覆盖**。表中的 Supported 来自上游清单/测试声明，不是本项目验收结果。[R5]

| MVP 必需能力 | 官方/源码证据 | 限制及待验证事项 |
|---|---|---|
| 桶与对象 CRUD | 矩阵列出桶 create/delete/list/head、对象 put/get/delete/copy/head、ListObjects/V2、用户元数据；`ecfs.rs` 存在对应 S3 trait 实现并委派到应用层。[R5][R15] | 覆盖原件和解析产物、内容校验、Content-Type/自定义元数据、空对象、特殊键、幂等与失败错误语义。不能仅检查接口入口存在。 |
| 预签名 GET/PUT | 矩阵列为 Supported；发布源码包含签名检查和负向回归。[R5][R11][R12] | 实际后端 SDK 与浏览器的 URL、Host、CORS、时钟、下载响应头、有效期、权限撤销行为待测。只成功上传/下载无法证明授权边界。 |
| Multipart | 矩阵支持 create/upload/complete/abort；S3 trait 包含相关入口，上游清单含内容完整性、缺 part、错误 ETag、小 part、重传等用例。[R5][R15][R16] | listing/part lookup 边缘用例不属于默认兼容 gate；节点不可用时 ListParts 可返回 503 `SlowDownRead`。覆盖并发、重复 part、断线、Complete/Abort 竞态与重启后恢复。 |
| 生命周期 | README 列 ILM 为 Available；S3 trait 存在配置 PUT/GET/DELETE；单独 behavior 清单包含当前/非当前版本过期、删除标记和 multipart 过期。[R5][R15][R17] | 配置被接收或重启后可读不证明对象已被回收；必须观察真实到期删除和空间/残留清理。上游部分过滤和 transition 测试仍 excluded/unimplemented。[R16][R18] |
| IAM、桶策略、服务账号 | README 列 IAM/Policies 为 Available；服务账号实现含创建、查询、更新、删除与父身份检查，官方文档列 session policy、过期和受限管理权限。[R9][R19] | 资源范围按桶/前缀验证。项目业务 ACL 仍由可信后端计算，不把持有存储 key 或 RustFS Console 身份视为 KB/Workspace 授权。 |
| STS | 发布源码实现 `AssumeRole` 和 `AssumeRoleWithWebIdentity`；普通 AssumeRole 拒绝临时/服务账号凭据，存储 session policy、父身份和有效期；时长默认 3600 秒，限制在 900–43200 秒。[R20] | 不是 AWS IAM 全功能替代。普通 AssumeRole 使用 `sts:AssumeRole` deny-only 检查；官方文档说明显式 Deny 拒绝、无需单独 Allow，且需有效绑定策略。验证策略交集、缺失上下文拒绝、过期与撤销，而非假定所有 AWS STS 语义相同。[R19][R20] |
| 删除与恢复 | 基本删除、版本及 delete marker 有实现和上游覆盖；RestoreObject 入口与官方 tier restore 文档存在。[R5][R15][R21] | `RestoreObject` 是 tiered 对象临时本地副本恢复，不等于误删恢复、备份恢复或 RAG 索引一致性恢复。按本项目删除生命周期验证原件、产物、版本、索引与备份策略。 |

明确的兼容边界包括：ACL 授权刻意不支持（canned ACL 部分入口不等于授权实现），桶 ownership controls 无 handler，bucket access logging 的测试仍列为未实现；对象键包含 `.`、`..` 或空路径段 `//` 被拒绝，版本桶中末尾 `/` 的目录 marker 使用 null version；批量删除可能 HTTP 200 内同时返回成功和逐对象错误。[R5][R22] 本项目按服务端资源 ACL 和策略授权，可避免依赖 S3 ACL，但仍要盘点实际 SDK 行为与对象键。

上游清单按非空、非注释行计数，`1.0.6` 为 implemented 459、unimplemented 21、excluded 275、独立 lifecycle behavior 5。[R16][R17][R18] 这些是测试入口的分类数量，存在厂商扩展和独立 gate，**不是“通过率”或已覆盖整个 S3 规范的百分比**；本次未检查每次 CI 执行结果。

RustFS 另有带入 SigV4 canonical query 的私有大小限制参数：`x-rustfs-max-content-length` 仅用于 presigned PutObject，`x-rustfs-max-total-object-size` 在创建 multipart 时持久化总量限制。[R23] 普通 S3 互通不要求采用它们；若未来确需服务端直接限制浏览器上传体积，将其封装在 Adapter 并实测，避免让领域契约依赖供应商查询参数。

## 5. 删除、生命周期、部署与迁移风险

### 5.1 生命周期与删除

- 上游 lifecycle behavior 用例独立运行，需要启用 scanner 和 `RUSTFS_ILM_DEBUG_DAY_SECS`；默认兼容测试与生命周期配置测试不等同真实过期行为验证。[R5][R17]
- `1.0.6` 运维文档说明未完成 multipart 默认 24 小时过期、每 6 小时清理，后台流程独立于 scanner/ILM；即使没有桶生命周期规则也可影响长时间上传，清理间隔并非空间回收时限保证。[R24] 需要覆盖服务重启、长上传、保守保留的残留与实际磁盘回收，不以 S3 listing 消失推导物理数据已清除。
- `1.0.5` 发布说明要求所有节点完成从 `1.0.4` 升级后再加删 pool/重试 decommission；新旧版本共存时新节点 DELETE 可能临时返回 HTTP 503。[R10] `1.0.6` 继续修复 MRF/scanner 待处理责任保留。[R2] 这是升级操作需要故障与数据一致性验收的实际理由，不能直接沿用 MinIO 滚动升级假设。

### 5.2 Docker 与平台

- `1.0.6` README 和 Dockerfile 对应 `linux/amd64`、`linux/arm64`；容器以 UID/GID `10001:10001` 运行，数据、日志与 TLS 挂载需要匹配权限，端口示例为 S3 9000/Console 9001。[R6][R25] 本次未验证 registry 中具体镜像 manifest 或 Apple Silicon 上的启动行为。
- Dockerfile 下载发布制品并核对 API 提供的 SHA-256；含 `RELEASE=latest`、独立 `RC_RELEASE=latest` 和构建时 `apk upgrade` 等动态输入。[R25] 若走自构建，需要固定服务端、rc、基础镜像/依赖与制品哈希；仅固定服务端 tag 并不能宣称全部构建输入可复现。
- 官方 software checklist 建议 Linux LTS、Linux 5.10+、x86_64/ARM；测试最少 2 GB RAM，生产建议 64 GB+；偏好专用盘、XFS 和 JBOD。[R26] 这些是官方建议，不能直接变成本项目已确认资源门槛，也不能由快速启动示例推导小内存生产适用性。
- SNSD（单节点单盘）仅支持独立本地路径，不能原地扩为 pool；多盘/多节点按 erasure geometry 扩 pool，接受配置不保证主机故障容忍。[R6] MVP 若选 SNSD，明确备份/恢复责任和后续迁移成本。
- 官方快速示例使用 `latest`、默认凭据或 Console CORS `*`；正式基线需要固定 digest、注入独立凭据、配置实际来源与网络范围，并检验日志脱敏。[R6][R25] 此研究没有复制示例修改项目部署。

### 5.3 MinIO 迁移与资料差异

`1.0.6` README 将 MinIO On-Disk Compatibility 标为 Preview 且笼统说明需 `rio-v2`；详细互操作文档却按制品区分：默认/full 可读未加密 `xl.meta`，可导入桶配置和 IAM；静态 KMS 的 SSE-S3/SSE-KMS、SSE-C 读取需专用 `rio-v2`，发布镜像不包含该变体，KES/MinKMS 等不支持；transitioned metadata 尚未 fixture-proven。[R6][R13] 两处范围表述不一致，应以具体 build、格式、来源版本和测试证据逐项判断，不能承诺“换镜像即可复用原卷”。

详细文档明确迁移单向：RustFS 写入的 drive set 给 live MinIO 读取 Unsupported（系统元数据目录等存在差异），RustFS 写入的 SSE 对象反向也不支持。[R13] 本项目若选择 RustFS，优先新数据卷通过 S3 复制与校验，保留源对象及配置以形成回滚路径；不要直接把 MinIO 原卷挂给 RustFS 后期待换回旧镜像恢复。普通 S3 复制还需核对用户元数据、标签、版本/删除标记和策略，不能假定单次 `cp` 保存全部语义。

动态文档和发布版本存在时间差：Docker 固定版本示例可停留在 `1.0.5`，GitHub latest 已为 `1.0.6`。[R2][R6] 以固定发布 tag 核验所需能力；`main` 功能表和文档站仅作为对照，不能代替发布制品验证。[R27] S3 Tables 不属于本项目 MVP 此次对象存储选型所需能力。

### 5.4 当前项目影响盘点

当前存储消费者集中在基础设施探针、初始化与 P0 持久化验收：

- [backend/app/adapters/infrastructure.py](../../../../backend/app/adapters/infrastructure.py) 使用 MinIO Python SDK 构建客户端并调用 `bucket_exists`。
- [scripts/infrastructure.py](../../../../scripts/infrastructure.py) 使用同一 SDK 初始化桶，并在 Compose 启动中检查/构建 MinIO 镜像；配置字段、profile 环境变量和服务命名也与 MinIO 耦合。
- [backend/tests/test_infrastructure.py](../../../../backend/tests/test_infrastructure.py) 使用 SDK 的 `put_object`/`get_object` 验证对象持久化与基础设施故障行为；该存量验收不能代替浏览器 presigned、multipart 或生命周期 POC。

同任务 2026-11-24 的只读本地盘点使用 `uv run --locked python`、`load_settings("development")` 与上述 SDK 配置，遍历 `client.list_objects(settings.minio_bucket, recursive=True)`，过滤目录项后计数并累加 `obj.size`，仅输出 `{"scope":"current project development bucket","objects":0,"bytes":0}`。该观察仅覆盖此桶当前可列出的对象，不覆盖其他桶、其他项目、版本历史或系统/IAM 目录状态，不能据此删除原卷。业务文档上传/解析模块尚未开发，源码搜索未发现 S3 bucket/object ACL API 调用。因业务存量较少、SDK 消费者较集中，当前形成兼容 Adapter 与新卷部署方案的成本相对较低；此判断仍以完整盘点与 POC 为准，不意味着后端资源 ACL、下载授权或迁移已实现。

同日核验 [MinIO Python SDK 官方仓库元数据](https://api.github.com/repos/minio/minio-py)，`archived=false`、`disabled=false`、最后推送为 `2026-09-28T08:08:04Z`。[R28] 社区服务端停止维护不能直接推导 SDK 同样归档。可先复用现有 SDK 验证 RustFS 的 S3 协议；最终客户端取舍仍需结合发布、安全维护和真实兼容结果，当前未更换 SDK。

## 6. POC-08 建议验证顺序与决定条件

1. **OBJ-01/06：固定候选与维护证据。** 固定 `1.0.6` 或执行时已复核的新稳定版、镜像 digest、目标架构、来源校验和依赖/制品扫描结果；记录最新版本安全更新方式、人员责任和更新窗口。复核上述公告的发布修复及实际制品，不以 Apache-2.0、Latest 或 Star 替代安全准入。
2. **OBJ-02：受限身份与签名。** 创建独立应用凭据，按桶/前缀控制读写删；覆盖 Deny、服务账号/session policy 不能扩大父权限、缺失/过期 token、管理端跨身份操作。用一次合法 presigned PUT 注入 unsigned CopySource/元数据等，验证既不能跨桶读取也不能改变未授权属性；对真实浏览器 CORS、Host 和过期行为回归。安全结论按既有门槛由非作者 Reviewer 检查。
3. **OBJ-03/04：项目 S3 兼容。** 用实际 SDK 验证原件、解析产物、用户元数据/内容校验、直接上传/下载和 multipart 完整链路。覆盖特殊键、校验头、失败错误语义、逐对象批量删除错误、重复与乱序 part、Abort/Complete 竞态、断线与重启后恢复；规模、并发和延迟门槛采用 MVP 已确认值，不沿用上游宣传基准。
4. **OBJ-05：到期、删除、故障和恢复。** 覆盖当前/非当前版本、删除标记、未完成 multipart 到期及真正空间回收，确认 scanner 关闭/失败时不会误判成功。中断 PUT/Complete/Delete 后重建并对账对象数、键、哈希、元数据与桶策略；执行配置和数据备份恢复，验证 RAG 原件/产物和业务状态一致。生产采用多盘时再覆盖该实际拓扑的磁盘/节点故障。
5. **OBJ-06/07：升级及迁移回滚。** 在隔离新卷演练旧/新版本升级，覆盖发行说明中的混合版本 DELETE 拒绝/重试；检查探针、初始化脚本、凭据注入、端口、挂载身份、日志与客户端适配。实际迁移前盘点源桶、对象、策略、加密与版本，复制后逐项校验；明确切换点和 S3 回迁/恢复步骤。

若必需授权、安全、S3、生命周期及恢复检查通过，且有持续维护和可执行迁移/回滚路径，RustFS 可形成“建议切换”的具体 ADR 方案交用户确认。若任一必需能力证据缺失，保持候选待验证；不能因为旧 MinIO 需要处置而降低新存储准入门槛。此次研究未改变 POC-08 状态或对象存储基线。

## 7. 一手来源

所有来源读取日期均为 2026-11-24；GitHub blob 链接固定发布标签，`main`、文档站和 API 为动态资料。

- [R1：官方仓库元数据](https://api.github.com/repos/rustfs/rustfs)。
- [R2：1.0.6 Release](https://github.com/rustfs/rustfs/releases/tag/1.0.6)；[latest API](https://api.github.com/repos/rustfs/rustfs/releases/latest)。
- [R3：官方 Release API，最近 100 条](https://api.github.com/repos/rustfs/rustfs/releases?per_page=100)。
- [R4：1.0.6 LICENSE](https://github.com/rustfs/rustfs/blob/1.0.6/LICENSE)。
- [R5：1.0.6 S3 Compatibility Matrix](https://github.com/rustfs/rustfs/blob/1.0.6/docs/architecture/s3-compatibility-matrix.md)。
- [R6：1.0.6 README](https://github.com/rustfs/rustfs/blob/1.0.6/README.md)；[发布 tree API](https://api.github.com/repos/rustfs/rustfs/git/trees/1.0.6?recursive=1)。
- [R7：1.0.6 Security Policy](https://github.com/rustfs/rustfs/blob/1.0.6/SECURITY.md)。
- [R8：官方公开安全公告 API](https://api.github.com/repos/rustfs/rustfs/security-advisories?per_page=100)。
- [R9：1.0.6 服务账号 handler](https://github.com/rustfs/rustfs/blob/1.0.6/rustfs/src/admin/handlers/service_account.rs)。
- [R10：1.0.5 Release 的升级说明](https://github.com/rustfs/rustfs/releases/tag/1.0.5)。
- [R11：1.0.6 认证源码](https://github.com/rustfs/rustfs/blob/1.0.6/rustfs/src/auth.rs)。
- [R12：1.0.6 预签名负向回归测试](https://github.com/rustfs/rustfs/blob/1.0.6/crates/e2e_test/src/presigned_negative_test.rs)。
- [R13：1.0.6 MinIO 磁盘格式互操作边界](https://github.com/rustfs/rustfs/blob/1.0.6/docs/architecture/minio-file-format-compat.md)。
- [R14：1.0.4 Release 的证书/依赖修复说明](https://github.com/rustfs/rustfs/releases/tag/1.0.4)。
- [R15：1.0.6 S3 trait 实现](https://github.com/rustfs/rustfs/blob/1.0.6/rustfs/src/storage/ecfs.rs)。
- [R16：1.0.6 implemented 测试清单](https://github.com/rustfs/rustfs/blob/1.0.6/scripts/s3-tests/implemented_tests.txt)；[unimplemented 清单](https://github.com/rustfs/rustfs/blob/1.0.6/scripts/s3-tests/unimplemented_tests.txt)。
- [R17：1.0.6 生命周期行为清单](https://github.com/rustfs/rustfs/blob/1.0.6/scripts/s3-tests/lifecycle_behavior_tests.txt)。
- [R18：1.0.6 excluded 测试清单](https://github.com/rustfs/rustfs/blob/1.0.6/scripts/s3-tests/excluded_tests.txt)。
- [R19：官方 Service Accounts and STS 文档](https://docs.rustfs.com/en/security-compliance/iam/sts)。
- [R20：1.0.6 STS handler](https://github.com/rustfs/rustfs/blob/1.0.6/rustfs/src/admin/handlers/sts.rs)。
- [R21：官方 Lifecycle Management 文档](https://docs.rustfs.com/en/administration/data/lifecycle-management)。
- [R22：1.0.6 MinIO/RustFS Router Compatibility](https://github.com/rustfs/rustfs/blob/1.0.6/docs/architecture/minio-rustfs-router-compatibility.md)。
- [R23：1.0.6 presigned 上传大小限制](https://github.com/rustfs/rustfs/blob/1.0.6/docs/operations/presigned-size-limits.md)。
- [R24：1.0.6 Scanner Runtime Controls，含 stale multipart 与 lifecycle 运行边界](https://github.com/rustfs/rustfs/blob/1.0.6/docs/operations/scanner-runtime-controls.md)。
- [R25：1.0.6 Dockerfile](https://github.com/rustfs/rustfs/blob/1.0.6/Dockerfile)；[docker-compose-simple.yml](https://github.com/rustfs/rustfs/blob/1.0.6/docker-compose-simple.yml)；[官方 Docker 安装文档](https://docs.rustfs.com/en/installation/container/docker)。
- [R26：官方 Software Checklist](https://docs.rustfs.com/en/installation/requirement/checklists/software-checklists)。
- [R27：官方 main README，动态对照资料](https://github.com/rustfs/rustfs/blob/main/README.md)。
- [R28：MinIO Python SDK 官方仓库元数据](https://api.github.com/repos/minio/minio-py)。
