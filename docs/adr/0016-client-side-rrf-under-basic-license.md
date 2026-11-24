---
status: accepted
date: 2026-11-24
---

# ADR-0016：Basic 许可下在 Search Adapter 中执行 RRF

当前 Elasticsearch `9.2.0` 使用有效 Basic 许可，原生 RRF 的实际只读查询返回 HTTP 403，提示 `current license is non-compliant for [Reciprocal Rank Fusion (RRF)]`。用户已同意保留 Elasticsearch，在 Search Adapter 内融合独立 Dense/BM25 排名；不以试用许可证作为日常运行前提。统一 Chunk ID 去重，按 `Σ 1/(rank_constant + rank)` 融合，保留分支排名用于诊断，RRF 分数不表示答案可信度。

两路召回在 ES 内执行相同的可信当前 KB/Document 范围、主体 ACL 标签、发布状态和业务筛选；返回候选再核对这些约束。缺失上下文、越界候选、超时、失败 shard 或无效响应拒绝返回。一次检索先解析单索引 read alias，再对同一物理索引发起两路查询，避免发布期间混用版本；旧索引的在途读取保护与生产清理仍需后续生命周期实现。

代价是多一次 alias 解析和两路查询，并在应用进程执行融合；候选数量和 HTTP 超时有界，真实容量、延迟和质量门槛待业务样本与 POC 冻结。P0-03 先验证内部 Adapter，P0-04/P1 接入正式 Retriever Contract 与可信 Identity/Policy；本次合成权限夹具不等于业务认证授权已交付。证据和剩余项见 [POC-01 实施记录](../plan/V1.0-MVP/implementation/POC-01-search.md)。
