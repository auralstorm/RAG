# POC-08：RustFS 权限、生命周期与备份恢复功能验收

日期：2026-11-24，Asia/Shanghai。状态：本地功能验收通过，完整 POC-08 与 M0 仍未关闭。选型和开发切换依据 [ADR-0015](../../../adr/0015-rustfs-object-storage.md) 与 [替换记录](rustfs-object-storage.md)。

## 范围与复现

在仓库根目录运行：

```bash
make poc-storage
```

[执行入口](../../../../scripts/poc/storage.py) 按 `uv.lock` 运行 [真实服务测试](../../../../backend/tests/test_storage_poc.py)，使用固定 RustFS 镜像与 [独立编排](../../../../infra/compose/storage-poc.yaml)。仅启动 `enterprise-rag-poc-storage` 和恢复阶段的 `enterprise-rag-poc-storage-restore`；后者使用空的新数据卷，源 POC 服务暂时停止以释放相同的测试端口。结束后删除两个 POC 项目的容器与卷，开发环境和 MinIO 源卷不参与。

测试复用 `.env.test` 的回环端口和本地根凭据，因此不能与 `make infra-test` 或其他占用 29000/29001 的测试同时运行。应用仍使用原 S3 Adapter；测试不会将管理员 SDK、STS 或身份管理引入业务接口。

报告保存在被 Git 忽略的 `.poc-results/storage/`：`report.json` 汇总运行 UTC 时间、版本、实际镜像 ID、Docker CPU/内存、输入文件 SHA-256、测试名称和结果；`results.xml` 保存 JUnit 结果，`lifecycle.json` 与 `backup.json` 保存测量摘要。每轮先清理上一轮报告，缺少测试、必要摘要或存在失败/跳过均不能判为 `FUNCTIONAL_PASS`。

## 已执行行为

| 用例 | 实际验证 |
|---|---|
| 受限应用身份 | 允许本前缀读写；同桶其他前缀的读写/删除、其他桶的读写被拒绝，受限身份不能调用用户管理 API |
| 批量删除 | 逐对象返回错误，允许对象被删除、拒绝对象内容保留；带 `../` 的字面对象键不影响其他前缀原件 |
| 凭据撤销 | 禁用用户后原访问被拒绝，恢复用户后可重新访问 |
| Service Account | 无管理权限的身份不能创建；有指定管理权限的身份可创建只读子账户；扩大子策略仍受父权限限制；跨 Owner 创建/更新被拒绝，禁用父身份后子账户访问被拒绝 |
| STS | 宽泛 Session Policy 不能扩大父身份的前缀/桶范围；只读 Session Policy 限制父身份的写权限；缺失/篡改 Token 被拒绝，禁用父身份后既有 Session 访问被拒绝 |
| 生命周期 | 按前缀配置过期，实际等待对象不可读，再检查 `/data` 中包括 trash 的 payload 哈希消失、目录占用下降；不匹配的对象仍可读取 |
| 备份恢复 | 通过 S3 导出当前对象与 manifest，再恢复到空的新卷；逐项核对数量、键、大小、SHA-256、Content-Type 和用户元数据；显式重建测试身份/策略后验证允许/拒绝，最后恢复源 POC 服务并复查源对象 |

Service Account 创建/更新使用固定 RustFS 镜像内的官方 `rc`，见 [POC CLI 桥接](../../../../backend/tests/storage_admin_cli.py)。当前 `minio-py` 的对应 Admin 方法与 RustFS 返回格式不完全兼容；桥接只限此 POC。调用参数通过 stdin 进入私有临时文件，容器内命令结束即删除，返回诊断掩码处理已提供的凭据。新测试身份、Service Account Secret 和 STS Token 仅用于合成数据，不进入版本控制或报告。

## 本轮证据

最终运行时间为 2026-11-24 06:20:57–06:21:36 UTC（Asia/Shanghai 14:20:57–14:21:36）。RustFS `1.0.6`，固定镜像摘要 `sha256:ee717072290bec9b11abfc0365f8310b00df1cd9b3639943edae47bdef05044a`，客户端 `minio==7.2.20`；Docker Desktop 为 linux/amd64、12 CPU、8,321,814,528 bytes 内存，RustFS 容器上限 2 GiB。

| 检查/测量 | 实际结果 |
|---|---|
| `make poc-storage` | 9 项测试通过，pytest 耗时 37.98 秒；`FUNCTIONAL_PASS`，无失败或跳过 |
| 生命周期 payload | 1,900,544 bytes；8.101 秒确认逻辑删除，8.581 秒确认 payload 哈希消失，`/data` 占用从 2324 KiB 降至 460 KiB；未匹配对象仍可读取 |
| 空新卷恢复 | 4 个当前对象，共 1,114,177 bytes；键、数量、内容、元数据及重建后的受限访问均符合断言 |
| Python 静态检查 | `uv run --locked ruff check backend scripts`、`ruff format --check backend scripts`、`pyright` 均通过，严格类型检查无错误 |
| 普通后端回归 | `uv run --locked pytest`：26 项通过；Docker POC/基础设施测试按 marker 排除 |
| 配置/文档 | `pnpm exec prettier --check infra/compose/storage-poc.yaml`、`uv run --locked python scripts/check_repository.py`、`git diff --check` 通过 |
| 环境清理 | 两个存储 POC 项目的容器与卷均已移除；既有六个开发依赖保持 healthy，旧 MinIO 与其他项目容器保持停止 |

## 验证边界与剩余任务

生命周期仅在 POC 覆盖 `RUSTFS_ILM_DEBUG_DAY_SECS=5`、扫描周期 2 秒，便于实际观察删除与空间下降；开发编排不含加速参数。该结果验证单节点功能，不冻结生产保留期、扫描延迟或文件系统压缩效果。

备份覆盖合成的当前对象与一份显式 IAM 策略重建，不包含版本历史、全量 IAM/Service Account/STS 导出、加密密钥或生产恢复时限。源与目标都为 RustFS，本测试不代表 RustFS 新数据回迁到 MinIO 已验收。

| 剩余项 | 关闭要求 |
|---|---|
| OBJ-02 独立安全结论 | 非作者 Reviewer 审查权限实现、测试范围和制品风险；本轮无独立评审 |
| OBJ-04 浏览器与规模 | 真实浏览器 CORS/预签名流、签署后的文件规模与并发门槛；本轮无容量/SLO 结论 |
| OBJ-05 生产恢复 | 适用的版本、完整配置/IAM、加密与实际部署故障/恢复演练及恢复时限 |
| OBJ-06 维护/供应链 | 制品扫描、签名/provenance、目标拓扑的升级/回滚与持续维护责任 |

上述剩余项由 Tech Lead / Platform 在 M0 冻结前按 [POC-08 关闭条件](../04-poc-acceptance-and-adr.md#114-关闭条件与执行顺序) 收敛；安全关键结论另需非作者 Reviewer。尚未签署的规模、并发和恢复门槛继续保持待确认，不能用本轮合成数据替代。
