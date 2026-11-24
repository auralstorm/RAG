# 03 — Agent Evaluation、测试体系与发布治理

> 公共字段、状态、事件、权限与迁移映射见 [统一契约与跨版本演进规则](../../architecture/统一契约与跨版本演进规则.md)；本文件描述本版能力及增量，具体实现须通过契约与升级验收。

## 1. 目标

V1.2 将“Agent 能运行”提升为“Agent 变更可验证、质量可比较、发布可控制、问题可回滚”。评测是发布流程的一部分，而不是发布后的可选报表。

## 2. 评测对象与层级

### 2.1 四层测试

| 层级 | 目标 | 示例 |
|---|---|---|
| Component | 单个能力正确 | Prompt 渲染、Tool Schema、Memory 摘要 |
| Integration | 组件协作正确 | Agent 调用 Retriever、Tool Gateway、Model Gateway |
| Scenario | 业务任务完成 | HR 政策问答、制度对比、请假余额查询 Mock |
| Governance | 权限、安全、成本与稳定性 | ACL 越权、Prompt Injection、预算超限、超时 |

### 2.2 测试集类型

- Golden Dataset：稳定回归集，发布必跑。
- Smoke Dataset：少量快速验证集。
- Adversarial Dataset：Prompt Injection、数据外泄、工具越权等安全样本。
- Tool Contract Dataset：参数边界、异常、超时、重试、幂等。
- Conversation Dataset：多轮指代、上下文摘要和记忆行为。
- Performance Dataset：并发、延迟、Token 与成本基准。

每个 Dataset 必须有版本、Owner、用途、标签、创建来源和变更记录。数据集样本中不得存放不必要的真实个人信息或生产秘密。

## 3. Evaluation 数据模型

### Dataset

- id、key、name、description、dataset_type
- version、status、owner_id、visibility
- schema_version、created_at、published_at

### Dataset Case

- id、dataset_version_id、case_key
- input_messages / input_variables
- expected_answer 或 assertions
- expected_citations（可选）
- expected_tool_behavior（可选）
- tags、severity、weight
- fixture_refs（Mock KB / Mock Tool 数据引用）

### Evaluation Profile

- 指标集合、评分器版本、阈值、超时、并发度
- 是否启用 Judge、Judge Model Profile
- 必测样本与失败严重级别规则

### Evaluation Run

- id、target_type（rag/agent）、target_snapshot、agent_id、agent_version_id、dataset_version_id
- profile_version_id
- status：queued / running / completed / failed / cancelled
- started_at、finished_at、initiator_id
- summary_metrics、report_object_key、trace_group_id
- DTO 的 report_uri 经访问授权从 Object Key 生成限时地址，不存永久公开 URL

### Evaluation Result

- case_id、evaluation_run_id、actual_output
- citations、tool_calls、policy_decisions
- metric_scores、assertion_results
- latency_ms、input_tokens、output_tokens、estimated_cost
- failure_category、trace_id；diagnostics 为受控报告详情，不与普通 Trace 混存

评测输入、输出和 Trace 应按数据生命周期策略处理；报告不能绕过原始会话和身份数据删除规则。

## 4. 指标体系

### 4.1 任务质量

- Task Success Rate：满足任务断言的样本比例。
- Answer Relevance：回答是否针对问题。
- Correctness：与标准答案或事实断言的一致性。
- Groundedness：回答是否有检索证据支持。
- Citation Validity：引用是否存在、可定位、内容支持结论。
- Completeness：是否覆盖任务要求。

### 4.2 Tool 行为

- Tool Selection Accuracy
- Tool Call Success Rate
- 参数 Schema 合法率
- 重试成功率
- Tool Latency
- 不必要调用率
- 重复副作用调用数
- Policy Deny / Allow 统计

### 4.3 治理与安全

- Unauthorized Tool Call：必须为 0 次成功越权。
- ACL Leakage：必须为 0。
- Prompt Injection Resistance：按安全测试集阈值。
- Sensitive Data Leakage：严重样本必须全部通过。
- Human Approval Compliance：需要审批的动作不得绕过。
- Secret Exposure：必须为 0。

### 4.4 性能与成本

- P50 / P95 / P99 Latency
- Tokens per Run
- Model Cost per Successful Task
- Tool Calls per Run
- Timeout / Error Rate
- Concurrency Saturation

指标必须定义分母、采样范围、失败处理和版本。不同 Dataset 或 Evaluation Profile 的结果不能直接比较，除非配置一致或明确标注差异。

## 5. 评分策略

采用混合评分；最小确定性 Scorer 与至少一种语义评分方式是 P0，RAGAS Adapter 接入适用的 RAG 语义指标，其他 Judge/校准/扩展指标可为 P1。评分器版本、输入映射、错误处理及指标分母在 Evaluation Profile 中固定；必选评分器未执行或失败则Run 标为 failed 并保留逐样本评分错误，阻断对应门禁，不将缺分视为通过。

职责：
- 确定性断言：字段、规则、引用 ID、Tool 参数、权限决策。
- 语义评分：Answer Relevance、Correctness、Completeness。
- Groundedness 评分：答案主张与证据对应关系。
- 人工复核：高风险业务、发布门禁争议和 Judge 低置信度样本。

LLM-as-a-Judge 需：
- 固定 Judge Prompt 版本和 Model Profile。
- 使用结构化输出 Schema。
- 对 Judge 结果保留依据和置信度。
- 对关键门禁使用规则断言，不把 Judge 单点结果作为唯一安全证据。
- 评测报告明确标注自动评分，不宣称等同人工真值。

## 6. 发布 Gate

建议按风险等级配置 Gate：

### 必须满足的硬门禁

- Definition Schema 验证通过。
- 所有必需资源可用且授权有效。
- 所有 Tool Contract 测试通过。
- ACL / Policy 安全测试无越权成功。
- 严重级别安全样本全部通过。
- 关键 Citation 验证通过。
- 不存在未审批生产写操作绑定。
- 必需评测样本执行完成。

### 可配置质量门禁

- Task Success Rate 不低于项目阈值。
- Groundedness / Citation Validity 达到阈值。
- 相对当前生产版本无超过容忍度的回归。
- P95 延迟和每次成功任务成本不超预算。
- 失败率、超时率低于阈值。

初始阈值应由 Golden Dataset 基线和业务风险确定。不要在缺乏真实数据时伪造一个通用百分比。首轮可先记录基线，再冻结项目阈值。

## 7. 回归比较

比较 Agent Version A 与 B 时：
- 使用相同 Dataset Version。
- 使用相同 Evaluation Profile Version。
- 固定或记录 Model Profile / Provider 版本。
- 对随机性参数、并发和重试策略进行控制。
- 展示总体指标、分标签指标、逐样本差异。
- 对新增失败和严重回归做突出提示。
- 记录不可比较因素，例如模型供应商升级或评测器版本变化。

## 8. 测试运行执行架构

```text
Admin Trigger
  -> Evaluation API
  -> Evaluation Job Queue (RabbitMQ)
  -> Celery Worker
  -> Agent Runtime (isolated run context)
  -> Tool Gateway / Retriever / Model Gateway
  -> Result Collector
  -> Scorers
  -> Evaluation DB + Object Storage
  -> Report / Release Gate
```

执行要求：
- Evaluation Run 有独立 Run ID 和 Trace Group。
- 评测 Worker 与在线 Chat Worker 分离队列或资源池，避免评测挤占生产流量。
- 对模型和工具调用实施并发、速率和成本限制。
- 失败样本可单独重试；重试不能重复真实副作用。
- 默认 Mock 外部写操作；不允许 Golden Dataset 直接操作生产业务系统。
- 支持取消和超时，取消后停止后续样本调度。
- 评测报告生成幂等。

## 9. 质量报告

报告至少包括：
- Agent / Version / Dataset / Profile 元信息
- 运行时间、样本数量、完成率
- 总体指标与分标签指标
- Gate 结果及未通过原因
- 与基线版本差异
- 失败样本列表和 Trace 链接
- Token、延迟、成本
- 评测器版本与限制说明

## 10. 数据与隐私

- Dataset 样本需脱敏，避免把员工真实会话直接复制为长期 Golden Dataset。
- Playground 和 Evaluation 的用户身份使用受控测试主体。
- 对敏感输入、输出和工具结果设置保留期限。
- 删除用户会话时，评测报告若含可识别个人信息，应按生命周期规则清理或脱敏。
- 匿名技术指标与可识别业务内容分离。
- 只读审计员可查看授权范围内的匿名报告，不能通过评测报告反向还原身份。

## 11. 验收标准

1. 支持创建、版本化和管理 Dataset。
2. 支持针对指定 Agent Version 执行评测。
3. 逐样本结果包含输出、引用、Tool、Policy、延迟和 Token。
4. 至少支持确定性断言和一种语义评分方式。
5. 能比较两个版本并展示回归样本。
6. 发布 Gate 可阻止硬门禁失败的版本。
7. 越权成功、ACL 泄露、秘密泄露等安全门禁为零容忍。
8. Evaluation 与在线流量资源隔离，支持限流、取消和重试。
9. 评测结果可追溯到 Agent Version、Dataset Version 和 Profile Version。
10. 报告遵循既定隐私和数据生命周期规则。

## 12. 跨版本数据与评分器兼容

V1.0 eval_* 迁移到本版 Dataset/Version/Case/Run/Result 的映射见统一契约第 6 节。评测对象区分 rag/agent；历史 RAG 任务保留 RAG 配置和索引快照，Agent/Version 可空，不能填造历史 Agent Version。Agent Gate 必须消费匹配版本及评分 Profile 的报告。

字段统一 profile_version_id、report_object_key、latency_ms、input_tokens/output_tokens；旧 DTO 有消费者时通过显式单位/结构映射兼容。V1.3 仅扩展规划/执行/协作指标并复用本版 Runner、报告和 Gate；没有平行建设义务。
