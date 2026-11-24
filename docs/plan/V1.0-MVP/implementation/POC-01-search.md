# POC-01：Elasticsearch Hybrid、ACL 与索引切换

- 日期：2026-11-24，UTC 时间见机器证据。
- 执行：Codex 本地；非作者安全评审待执行。
- 决策：[ADR-0016](../../../adr/0016-client-side-rrf-under-basic-license.md)。
- 状态：独立真实 ES 的合成功能验证；完整 POC-01 的业务质量、负载与安全准入尚未关闭。

## 范围与可复现入口

```bash
make poc-search
make check
```

`make poc-search` 只管理 `enterprise-rag-poc-search` 的单个 Elasticsearch 服务，继承 [已锁定 ES 编排](../../../../infra/compose/search-poc.yaml)，使用测试端口 29200 和自己的数据卷；结束后清理该项目。开发环境和 `enterprise-rag-test` 不参与停止或清理。完整运行证据写入被 Git 忽略的 `.poc-results/search/`，包含报告、JUnit 和环境；本次报告见 [机器证据](evidence/POC-01-search-local.json)，包含固定镜像、环境、UTC 时间、数据集 SHA-256 与测试列表，不包含模型凭据。

[合成数据](../../../../backend/tests/fixtures/search-poc.json) 包含 8 个 Chunk：允许文档、不同 KB、不同主体、索引 ACL 与当前授权不一致、草稿和删除状态。向量固定为 3 维 cosine，编号/文本与预期结果人工指定；这不是用户文档解析结果、百炼 Embedding 或业务 Golden Dataset。实际模型计划为 `qwen3.7-text-embedding-flash` 默认 1024 维；生产 ES 维度必须按真实调用返回值与模型配置核对。

## 实施与功能证据

- [Search Adapter](../../../../backend/app/adapters/elasticsearch.py)：两路 ES 原生召回，应用内 RRF；没有新增供应商 SDK 或业务 HTTP 路由。
- [真实服务验收](../../../../backend/tests/test_search_poc.py)：Basic 许可及原生 RRF 403、Dense/BM25、精确编号、无关键词重合、Metadata、KB/主体与发布状态过滤、索引标签未更新时的当前授权撤回、缺失上下文、向量维度错误、原子 alias 发布/回滚、多索引 alias 拒绝及并发读取。
- [融合验收](../../../../backend/tests/test_search_ranking.py)：独立手算例、重复 Chunk、同分稳定排序、空分支与无效常数。
- [失败验收](../../../../backend/tests/test_search_failures.py)：缺失授权在 I/O 前拒绝；超时、失败 shard、越界候选、无效响应和连接失败不返回候选；取消向调用方传播。

| 检查 | 实际结果 |
|---|---|
| `make poc-search` | 12 项真实 ES 测试通过，pytest 耗时 73.67 秒，机器结论为 FUNCTIONAL_PASS；POC 容器、网络及卷已清理 |
| `make check` | Ruff/ESLint、格式、Pyright/TypeScript、26 项普通后端测试、6 项前端测试、Chat/Admin 构建和仓库/差异检查通过；既有 Vite chunk-size 提示保留 |
| 故障与恢复 | 仅停止隔离 POC 的 ES，检索明确失败；重新启动后原索引、alias 与授权查询结果保持一致 |
| 索引并发切换 | 20 次读取与 20 次 alias 切换交错执行，返回文档版本始终来自本次固定物理索引；错误的多索引 read alias 被拒绝 |
| 授权边界 | 当前允许文档/KB 与主体标签、发布状态、Metadata 条件共同作用；低 candidate_k 场景仍能召回允许项；撤回当前文档权限后旧索引标签不能恢复访问 |
| TDD 过程 | RRF 手算用例先因缺少实现失败，再通过；真实 ES 的首个检索用例先因缺少 Adapter 类型失败，实现后通过；后续场景使用公开 Adapter/ES 接口与 HTTP 系统边界验收 |

检索服务六项开发依赖在验收后复查全部就绪；远程 CI 配置新增 `make poc-search`，服务端执行与非作者评审仍待实际进行。

## 明确的验收边界

当前授权范围由合成 Policy 夹具提供，验证的是“可信当前范围传入 Adapter 后，召回前过滤及撤权约束成立”。尚未实现真实登录、组织/角色/KB 权限推导、数据库撤权传播或 API 授权，相关正式契约在 P0-04/P1 交付，安全结论需非作者 Reviewer 审查。

ES-01/02/03/04 的功能与融合方式、ES-05/06 的夹具边界、ES-07/08 的维度及索引切换按本轮实际证据记录；ES-09 的目标容量、真实 Embedding、中文分词/编号质量、Recall@K、P95/P99 与错误率门槛仍待业务样本及容量确认。ES-10 已验证隔离单节点服务的停机拒绝与重启恢复；这不代表磁盘/节点集群容错。旧物理索引保留到在途请求完成、索引验证与清理、跨数据库/ES 的发布一致性均需后续真实业务实现。

技术风险负责人沿用 Tech Lead / Platform / RAG，在 M0 冻结前确认质量、容量、性能和安全评审结果；没有实测/批准的门槛不填写 PASS。
