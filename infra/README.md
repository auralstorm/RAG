# 本地 Docker 开发环境

在仓库根目录运行 `make infra-up`，启动 PostgreSQL、Redis、RabbitMQ、Elasticsearch、RustFS 与 Phoenix，并初始化对象存储桶。首次启动会生成 `infra/compose/.env.development`，权限为 0600；该文件包含随机本地凭据，已被 Git 忽略。再次使用时保留既有配置和密码。

Docker Desktop 建议分配至少 8 GB 内存，以同时运行开发/测试依赖。首次启动需下载固定摘要镜像，之后复用本地缓存。资源限制、卷、健康检查及 Phoenix 的数据库启动依赖见 [Compose 配置](compose/compose.yaml)。

## 命令与数据生命周期

| 命令 | 行为 |
|---|---|
| `make infra-up` | 启动开发服务，等待健康检查，幂等初始化存储桶 |
| `make infra-status` | 查看本项目开发服务的状态 |
| `make infra-init` | 仅创建缺失的配置，保留既有凭据 |
| `make infra-down` | 停止并移除本项目开发容器及网络，保留数据卷 |
| `make infra-reset` | 清空本项目开发数据卷，再重新启动；会删除该环境中的数据 |
| `make infra-test` | 在独立测试环境验证持久化、故障与重置，结束后清理测试卷；测试数据会被丢弃 |
| `make poc-storage` | 在独立 RustFS POC 项目验证权限、生命周期回收及新卷备份恢复，结束后清理 POC 卷；使用相同测试端口，不能与 `make infra-test` 同时运行 |

管理命令可用 `PROFILE=test` 选择测试环境，例如 `make infra-status PROFILE=test`。脚本只接受 `development` 和 `test`，分别绑定 `enterprise-rag-dev`、`enterprise-rag-test` Compose 项目，不管理其他项目的容器或卷。

## 本地端口

所有发布端口仅绑定 `127.0.0.1`。

| 服务 | 开发端口 | 测试端口 |
|---|---:|---:|
| PostgreSQL | 15432 | 25432 |
| Redis | 16379 | 26379 |
| RabbitMQ AMQP | 15673 | 25673 |
| RabbitMQ 管理界面 | 15672 | 25672 |
| Elasticsearch | 19200 | 29200 |
| RustFS S3 | 19000 | 29000 |
| RustFS 控制台 | 19001 | 29001 |
| Phoenix | 16006 | 26006 |
| Phoenix OTLP gRPC | 14317 | 24317 |

Phoenix 使用 PostgreSQL 的独立 `phoenix` 数据库；Redis 开启 AOF，RabbitMQ 使用稳定节点名称。数据保存在各 Compose 项目自己的命名卷中。

## API 就绪检查

启动依赖后运行 `make dev-backend`。应用读取 `.env` 的应用配置，再读取所选环境的基础设施配置；进程环境变量优先。默认选择开发环境，测试环境使用 `ENTERPRISE_RAG_INFRA_PROFILE=test`。

- `/health/live`：API 进程能响应请求即返回 200。
- `/health/ready`：并发检查六个真实依赖；全部成功返回 200，否则返回 503，并提供每项依赖的布尔状态。未配置基础设施时也返回 503。
- 检查具有超时上限，结果不包含连接地址、密码或原始异常；共享客户端在应用生命周期中创建和关闭。

这是开发/测试编排：Elasticsearch 本地单节点关闭认证，其他服务使用生成的本地凭据。生产认证、TLS、容量和运维策略在对应交付任务中配置。

## 镜像与 S3 客户端

所有公开镜像按 [images.env](compose/images.env) 的 SHA-256 摘要固定。RustFS `1.0.6` 使用官方 `rustfs/rustfs` 镜像，不再构建旧 MinIO 服务端。RustFS 数据和日志分别存于 `rustfs-data`、`rustfs-logs` 新卷；启动前由同一固定镜像的离线辅助容器将卷根目录属主设置为 `10001:10001`，服务以该非 root 身份运行。开发单节点单盘内存上限为 2 GiB，这不是生产容量或容错保证。

S3 客户端统一位于 [object_storage Adapter](../backend/app/adapters/object_storage.py)，继续使用维护中的 `minio==7.2.20` Python SDK，连接池超时及资源释放在 Adapter 管理。该包是协议客户端；实际对象存储服务为 RustFS。其他探针使用 Psycopg、Redis、aio-pika 与 httpx2，版本见 `backend/pyproject.toml` 和 `uv.lock`。Redis PING 的未声明类型 kwargs 仅在具体调用行忽略，保留其余严格类型检查。

选型依据见 [ADR-0015](../docs/adr/0015-rustfs-object-storage.md)，实际替换验证见 [实施记录](../docs/plan/V1.0-MVP/implementation/rustfs-object-storage.md)。生产维护、安全、授权、生命周期与恢复准入仍按 [POC-08](../docs/plan/V1.0-MVP/04-poc-acceptance-and-adr.md#11-poc-08-对象存储维护安全与选型复核) 处理。

## 配置兼容与旧数据保护

新配置使用 `ENTERPRISE_RAG_OBJECT_STORAGE_ENDPOINT/ACCESS_KEY/SECRET_KEY/BUCKET` 及 Compose 的 `OBJECT_STORAGE_PORT/OBJECT_STORAGE_CONSOLE_PORT`。`make infra-init` / `make infra-up` 发现旧 profile 时先保存 `.env.<profile>.pre-rustfs`（0600），再追加新名称并原子替换 profile；原有密码、端口和其他服务配置保留。新名称已存在时优先使用，重复运行不会再改写。旧 `ENTERPRISE_RAG_MINIO_*` 作为 Settings 环境兼容别名保留，建议新配置统一使用新名称；进程环境优先于配置文件。

`make infra-up` 启动前核对后端解析的端点和凭据是否与 Compose 的 RustFS 配置一致。存在冲突时先移除旧别名覆盖或统一为匹配的规范变量。`make poc-storage` 使用当次生成的凭据和经 Compose 验证的回环端点。

配置升级不复制对象，也不自动停止旧 MinIO。首次从已有 MinIO 切换时，先盘点所有桶、版本、策略/加密，验证新 RustFS 卷，再停止本项目旧容器释放端口。存在对象或版本时先按 S3 迁移并逐项校验，不直接挂载 MinIO 原卷。本次开发桶为空，旧 `enterprise-rag-dev_minio-data` 卷及镜像保留，旧服务停止。

`make infra-down` 保留活动数据卷；`make infra-reset` 只删除当前 Compose 定义的卷，包括 RustFS 数据与日志，**不删除已退出编排的 MinIO 原卷**。原 MinIO Dockerfile 仅保留历史构建/回退用途。不要使用 `--remove-orphans` 清理未盘点的旧容器。

就绪接口的依赖名称由 `minio` 改为供应商无关的 `object_storage`。当前消费者为本仓库测试与运维说明，均已同步；外部监控接入时使用新名称。

## MinIO 源卷回退

仅适用于此次空桶切换或停止写入且确认无需保留 RustFS 新数据的开发环境。若 RustFS 已有新对象、版本或策略，先暂停写入并通过 S3 回迁/备份恢复、校验，再执行回退。旧 MinIO 存在已记录的维护与安全问题，回退只用于隔离开发排障，不能据此部署生产。

在仓库根目录执行，保留所有新旧数据卷：

```bash
# Stop RustFS, preserving its volumes.
uv run --locked python -c 'from scripts.infrastructure import compose; compose("development", "stop", "rustfs")'

# Reuse only the untouched MinIO source volume and private legacy credentials.
MINIO_ROLLBACK_VOLUME=enterprise-rag-dev_minio-data docker compose \
  --project-name enterprise-rag-dev \
  --file infra/compose/minio.rollback.yaml \
  --env-file infra/compose/.env.development.pre-rustfs \
  up --detach --wait
```

回到 RustFS：

```bash
MINIO_ROLLBACK_VOLUME=enterprise-rag-dev_minio-data docker compose \
  --project-name enterprise-rag-dev \
  --file infra/compose/minio.rollback.yaml \
  --env-file infra/compose/.env.development.pre-rustfs \
  stop minio
make infra-up
```

这些命令不自动对账或同步回退期间的新写入。回退配置将原卷声明为 external，不能把 RustFS 的卷名填入 `MINIO_ROLLBACK_VOLUME`。
