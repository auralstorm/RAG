---
status: accepted
date: 2026-11-24
---

# ADR-0015：RustFS 替换 MinIO，保持 S3 与平台模型边界

MinIO 社区服务端已停止维护，原 P0-02 固定版本也早于已知安全修复。用户在阅读 [一手资料研究](../plan/V1.0-MVP/research/rustfs-object-storage.md) 后明确决定采用 RustFS；项目所有版本的对象存储基线统一为 **RustFS，通过 S3 协议接入**。采用持续维护的 Apache-2.0 服务端，接受其稳定发行历史较短、最新版本更新政策及部分 S3 兼容限制；不再将旧 MinIO 的源码构建作为日常启动依赖。

开发/测试环境固定 RustFS `1.0.6` 与 [实际镜像 digest](../../infra/compose/images.env)，使用单节点单盘、独立数据和日志卷、UID/GID `10001:10001` 及仅回环端口。该部署不提供磁盘/主机容错；生产拓扑与容量依实际 POC 冻结。现有 `minio==7.2.20` Python 包继续作为 S3 **客户端 SDK**，统一封装在 Adapter；保留该包不代表仍使用 MinIO 服务端。后端就绪项统一为 `object_storage`，配置统一为 `OBJECT_STORAGE_*`，旧 `MINIO_*` 环境变量作为兼容别名保留，生成的旧 profile 在私有备份后追加新名称，保留既有密码。

平台继续自主控制 Document、Chunk、KB/Workspace 与资源 ACL。RustFS 不提供完整 S3 ACL 授权，应用按可信服务端 Policy 控制资源；对象存储凭据和 Console 身份不能替代业务授权。本决策不引入客户租户、STS 业务接口或后续版本能力。

迁移采用新卷，避免 MinIO 磁盘兼容的单向写入风险；本次源桶盘点为无对象/版本历史、未启用版本、无桶策略，因此不需要对象复制。保留原 MinIO 卷、镜像和 `0600` 配置备份，提供 [人工回退入口](../../infra/README.md#minio-源卷回退)。RustFS 上的新写入不能通过换回旧卷恢复，存在新数据时必须先通过 S3 回迁、校验并另行演练，不把空桶切换等同于存量迁移方案已经验收。

选型已批准，开发运行证据见 [替换实施记录](../plan/V1.0-MVP/implementation/rustfs-object-storage.md)。[POC-08](../plan/V1.0-MVP/04-poc-acceptance-and-adr.md#11-poc-08-对象存储维护安全与选型复核) 继续完成受限身份/STS、签名有效期及浏览器 CORS、真实生命周期回收、备份恢复、规模/并发、升级、供应链扫描与非作者安全评审；本 ADR 不宣称这些检查或生产准入已经通过。
