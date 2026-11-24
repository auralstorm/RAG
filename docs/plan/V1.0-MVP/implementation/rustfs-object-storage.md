# RustFS 对象存储替换实施记录

- 日期：2026-11-24，Asia/Shanghai。
- 范围：用户已确认以 RustFS 替换 MinIO，更新开发/测试基线、S3 Adapter、配置兼容、探针、验收及相关文档。
- 决策：[ADR-0015](../../../adr/0015-rustfs-object-storage.md)。
- 验证状态：本地代码与独立基础设施验收通过；开发运行和回退结果见下表。开发六依赖 ready/live 复查均通过。完整 POC-08 与生产准入仍待验证。

## 源数据与兼容

切换前通过实际 S3 SDK 列举全部桶、递归对象及版本、查询版本配置和桶策略：仅有 `enterprise-rag` 桶，对象及版本记录 0、0 bytes，版本未启用、无桶策略。因此此次无需复制对象；该结果不代表系统/IAM 元数据为空，原卷仍保留。

- 原 MinIO 卷 `enterprise-rag-dev_minio-data` 与原本地镜像保留，RustFS 不挂载该卷。
- 开发和测试 profile 在 `.env.<profile>.pre-rustfs` 私有备份后追加 `OBJECT_STORAGE_*`，备份及改写文件均为 0600；其他密码、端口、注释保留，重复初始化不改写。
- RustFS 使用独立 `rustfs-data` / `rustfs-logs` 命名卷、UID/GID 10001；启动辅助容器仅对新卷根设置属主。
- 就绪 JSON 的 `minio` 项改为 `object_storage`；已核对消费者仅为本仓库测试和说明。
- 复用 `minio==7.2.20` S3 客户端，实际服务端改为 RustFS；业务模型和资源 ACL 不变。

## 固定制品与环境

镜像索引 digest 为 `sha256:ee717072290bec9b11abfc0365f8310b00df1cd9b3639943edae47bdef05044a`，amd64 manifest 为 `sha256:0dff1515b3c52b5ce8c5df2263420c7f93ae1c5d07cca79e19e57cff86b84c85`；索引还包含 arm64，但本次只运行 Docker Desktop 的 linux/amd64。容器二进制 `rustfs --version` 返回 `1.0.6`、release、linux-x86_64/musl、官方发布提交 `de9009d882644effc2628e777650025c3d8e7c65`。Docker 分配 12 CPU、约 8 GB RAM，RustFS 服务内存上限 2 GiB；这是本地功能验收环境。

直接查询 `registry-1.docker.io` 和 Docker Hub API 发生 TCP connection reset，daemon 的首次拉取停滞。使用已配置加速路径 `docker.m.daocloud.io/rustfs/rustfs:1.0.6@sha256:ee717072290bec9b11abfc0365f8310b00df1cd9b3639943edae47bdef05044a` 获取固定内容后，再执行官方名称 `docker pull rustfs/rustfs:1.0.6@sha256:ee717072290bec9b11abfc0365f8310b00df1cd9b3639943edae47bdef05044a` 成功；镜像 RepoDigests 包含两个名称下相同摘要。活动配置保持官方名称和摘要。索引/层摘要和二进制版本的核验不替代制品签名、provenance 与 SBOM 漏洞扫描。

## 可复现验证

```bash
make check
make infra-test
make infra-up
make infra-status
```

基础设施测试使用独立 `enterprise-rag-test` 项目和测试端口；结束后删除测试卷，开发数据不参与重置。测试内容见 [基础设施验收](../../../../backend/tests/test_infrastructure.py)、[S3 协议验收](../../../../backend/tests/storage_protocol.py) 和 [配置迁移验收](../../../../backend/tests/test_storage_config.py)。

| 检查 | 实际结果 |
|---|---|
| `make check` | Ruff/ESLint、格式、Pyright/TypeScript、13 项普通后端测试、6 项前端测试、Chat/Admin 构建及仓库/差异检查通过；Vite 保留既有 chunk-size 提示 |
| 更新后的配置优先级测试 | `uv run --locked pytest backend/tests/test_storage_config.py`：4 项通过；Pyright、Ruff lint/format 通过，涵盖旧进程环境覆盖迁移后的 profile |
| `make infra-test` | 1 项完整集成验收通过，耗时 499.69 秒；使用隔离测试项目，最终容器和测试卷已清理 |
| S3 协议 | 6,600,000 bytes 固定数据，SDK 的 5 MiB part size 触发两段上传；内容 SHA-256、Content-Type、用户元数据和空对象通过 |
| 预签名与拒绝 | GET/PUT 成功；过期、对象键篡改、匿名读取、方法变更、未签名 `x-amz-copy-source` 注入均返回 403；注入后原对象内容未改变，删除后 GET 返回 404 |
| 持久化及故障 | PostgreSQL 行、Redis Key、RabbitMQ 持久消息、ES 文档、RustFS 对象在 down/up 后一致；逐项停止六服务，ready 返回 503/对应依赖 false、live 仍 200，恢复后 ready 返回 200；重置后重新初始化成功 |
| 开发启动 | `make infra-up` 新 RustFS 卷和两端健康检查通过，bucket 幂等初始化完成；原五服务容器 ID 保留 |
| MinIO 源卷回退 | 按仓库 rollback Compose 启动保留的原卷，读取空桶成功；停止 MinIO 后恢复 RustFS，未交叉挂载或删除卷 |

回退演练期间的一次就绪检查与停机发生重叠，返回 503；之后复查发现开发 RabbitMQ/Phoenix 的宿主机端口空响应，容器内端口/health 正常。定向重启这两个既有容器以恢复端口路径，保留 ID、卷及凭据；该现象的完整 Docker 根因尚未证明。恢复后的实际 FastAPI TestClient 复查：`/health/live` 与 `/health/ready` 均为 200，六项依赖全部 true；就绪响应未包含配置凭据，RustFS 启动日志未包含 Secret Key。保留该异常记录，不将其归因于 RustFS 镜像或修改探针以绕过失败。

开发 PostgreSQL/Redis/RabbitMQ/Elasticsearch/Phoenix 容器 ID 与切换前一致，仅 RabbitMQ/Phoenix 为端口恢复进行了重启；既有其他项目的 `rag-qdrant-1`、`rag-postgres-1`、`rag-redis-1` 保持任务开始时的 ID 和停止状态。原 MinIO 回退容器最终停止，旧数据卷与私有配置备份均保留，备份未纳入 Git。

## 回退与剩余验收

回退入口与命令见 [基础设施说明](../../../../infra/README.md#minio-源卷回退)。仅回到保留的 MinIO 原卷不包含 RustFS 上的新写入；存在新数据时先暂停写入、通过 S3 回迁和校验，不能交叉挂载卷。

本次完成开发基线替换。后续 [POC-08 功能验收](POC-08-storage.md) 已验证受限应用身份、Service Account/STS 权限交集、加速生命周期的 payload 回收与当前对象的新卷备份恢复。真实浏览器 CORS、生产保留期/完整备份、规模并发、实际拓扑升级/故障、制品扫描/签名及非作者安全评审仍待完成。日常开发可继续；P0-03/M0 不能据此勾选全部技术 POC 通过。
