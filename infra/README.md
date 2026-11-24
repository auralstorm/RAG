# 本地 Docker 开发环境

在仓库根目录运行 `make infra-up`，启动 PostgreSQL、Redis、RabbitMQ、Elasticsearch、MinIO 与 Phoenix，并初始化对象存储桶。首次启动会生成 `infra/compose/.env.development`，权限为 0600；该文件包含随机本地凭据，已被 Git 忽略。再次使用时保留既有配置和密码。

Docker Desktop 建议至少分配 6 GB 内存。首次启动需下载镜像和构建 MinIO，之后复用本地缓存。资源限制、卷、健康检查及 Phoenix 的数据库启动依赖见 [Compose 配置](compose/compose.yaml)。

## 命令与数据生命周期

| 命令 | 行为 |
|---|---|
| `make infra-up` | 启动开发服务，等待健康检查，幂等初始化存储桶 |
| `make infra-status` | 查看本项目开发服务的状态 |
| `make infra-init` | 仅创建缺失的配置，保留既有凭据 |
| `make infra-down` | 停止并移除本项目开发容器及网络，保留数据卷 |
| `make infra-reset` | 清空本项目开发数据卷，再重新启动；会删除该环境中的数据 |
| `make infra-test` | 在独立测试环境验证持久化、故障与重置，结束后清理测试卷；测试数据会被丢弃 |

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
| MinIO S3 | 19000 | 29000 |
| MinIO 控制台 | 19001 | 29001 |
| Phoenix | 16006 | 26006 |
| Phoenix OTLP gRPC | 14317 | 24317 |

Phoenix 使用 PostgreSQL 的独立 `phoenix` 数据库；Redis 开启 AOF，RabbitMQ 使用稳定节点名称。数据保存在各 Compose 项目自己的命名卷中。

## API 就绪检查

启动依赖后运行 `make dev-backend`。应用读取 `.env` 的应用配置，再读取所选环境的基础设施配置；进程环境变量优先。默认选择开发环境，测试环境使用 `ENTERPRISE_RAG_INFRA_PROFILE=test`。

- `/health/live`：API 进程能响应请求即返回 200。
- `/health/ready`：并发检查六个真实依赖；全部成功返回 200，否则返回 503，并提供每项依赖的布尔状态。未配置基础设施时也返回 503。
- 检查具有超时上限，结果不包含连接地址、密码或原始异常；共享客户端在应用生命周期中创建和关闭。

这是开发/测试编排：Elasticsearch 本地单节点关闭认证，其他服务使用生成的本地凭据。生产认证、TLS、容量和运维策略在对应交付任务中配置。

## 镜像与源码固定

公开镜像按 [images.env](compose/images.env) 的 SHA-256 摘要固定。MinIO 官方镜像地址在本次环境中无法拉取，改由 [Dockerfile](docker/minio/Dockerfile) 构建相同供应商的固定发行源码。

MinIO 源码为官方 `RELEASE.2025-09-07T16-13-09Z`，归档 SHA-256 为 `c9598dcce3440977e79f787f2ba0e7e4d92c8d556bd51e7cef3785bafd6635f3`。Go、Alpine 基础镜像同样按摘要固定，构建会验证源码校验值。首次编译需要网络获取校验过的 Go 依赖，已有本地镜像时启动不会重新编译。

探针使用 Psycopg、Redis、aio-pika、MinIO 与 httpx2，版本由 `backend/pyproject.toml` 和 `uv.lock` 管理。Redis PING 方法存在未声明类型的可选 kwargs，仅在该 SDK 调用行忽略 `reportUnknownMemberType`，保留结果检查和全局严格类型检查。
