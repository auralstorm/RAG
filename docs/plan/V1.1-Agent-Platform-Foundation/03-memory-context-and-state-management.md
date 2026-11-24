# 03｜Memory、Context 与 Agent State 管理设计

> 公共字段、状态、事件、权限与迁移映射见 [统一契约与跨版本演进规则](../../architecture/统一契约与跨版本演进规则.md)；本文件描述本版能力及增量，具体实现须通过契约与升级验收。

**版本：** V1.1 — Agent Platform Foundation  
**状态：** 研发设计基线  
**定位：** 建立可控的会话上下文、任务状态和基础记忆能力；不提前建设复杂长期个性化记忆系统。

---

## 1. 设计目标

V1.1 解决 Agent 执行中上下文如何构建、压缩、恢复和治理的问题。Memory 不等于把所有历史聊天永久塞入 Prompt，也不等于 LangGraph Checkpoint。

本版本实现：
- Conversation Context：当前对话上下文；
- Run State：单次 Agent 执行状态；
- Checkpoint：执行中断恢复所需状态；
- Summary Memory：长对话摘要；
- Task Memory：当前任务内事实、决策和中间结果；
- Token Budget Manager：模型上下文和成本预算；
- 生命周期与删除规则。

本版本不实现：
- 跨用户共享记忆；
- 自动推断并永久保存敏感个人偏好；
- 复杂知识图谱记忆；
- 多 Agent 共享长期记忆；
- V1.2 的 Agent 级记忆配置界面。

## 2. 概念区分

| 类型 | 用途 | 生命周期 | 事实来源 |
|---|---|---|---|
| Conversation Messages | 对话原文和交互记录 | 按平台会话政策 | PostgreSQL/受控存储 |
| Conversation Summary | 历史对话压缩摘要 | 随会话生命周期 | 摘要任务产物 |
| Run State | 当前执行中的变量和进度 | Run 生命周期 | Runtime |
| Checkpoint | 从中断处恢复 | 按 Run 保留策略 | Checkpoint Store |
| Task Memory | 当前任务已确认事实、结果引用 | 任务生命周期 | Runtime/Tool/RAG 结果 |
| User Preference Memory | 用户显式偏好 | 本版本仅预留接口 | 用户确认/后续治理 |
| Knowledge Evidence | 企业知识依据 | KB/Document 生命周期 | RAG Engine |

不要把 Evidence、模型猜测和用户偏好混成同一类记忆。

## 3. Context Assembly

上下文构建顺序建议：
1. 系统级安全指令；
2. Agent 固定指令；
3. 可信运行元数据（只注入必要且不暴露给模型的部分）；
4. 当前用户请求；
5. 当前任务状态摘要；
6. 必要的历史消息或会话摘要；
7. RAG Evidence；
8. Tool Result（经过脱敏和 Schema 标准化）；
9. 输出格式要求。

可信身份、权限决策、Secret 和策略内部细节不应放入模型可修改的上下文。

## 4. Token Budget Manager

### 4.1 预算公式

可用输入预算：

`input_budget = model_context_window - reserved_output_tokens - safety_margin`

再按优先级分配：
- System/Agent Instructions：固定保留；
- Current User Request：固定保留；
- Evidence：按相关性与证据质量；
- Recent Messages：按时间与任务相关性；
- Summary：作为历史压缩；
- Tool Results：只保留当前任务必要字段。

预算必须依据 Model Gateway 返回的模型能力元数据，不允许在代码中对所有模型写死同一个上下文窗口。

### 4.2 超限处理顺序

1. 去除无关历史消息；
2. 对旧消息使用摘要；
3. 缩短 Tool Result，只保留 Schema 中必要字段；
4. 减少低相关 Evidence；
5. 必要时请求用户拆分问题或明确范围；
6. 若仍超限，返回明确错误，不静默截断系统指令或关键证据。

## 5. Summary Memory

### 5.1 摘要内容结构

建议结构：
- `conversation_goal`：对话目标；
- `confirmed_facts`：用户明确提供或系统证据支持的事实；
- `open_questions`：待澄清问题；
- `decisions`：用户明确确认的决定；
- `evidence_refs`：证据引用 ID；
- `updated_at`；
- `summary_version`。

摘要必须区分：
- 用户明确陈述；
- 工具/知识库证实；
- 模型推断；
- 尚未验证。

禁止将模型猜测写成 confirmed fact。

### 5.2 更新机制

- 达到消息数量或 Token 阈值时异步触发摘要。
- 新摘要先生成临时版本，通过结构校验后再替换当前版本。
- 摘要失败不应导致原会话不可用。
- 重要决策应保留原始消息引用，摘要不能成为唯一证据。
- 对敏感信息执行脱敏/排除规则。

## 6. Task Memory

Task Memory 只服务当前 Agent Run：
- 已完成步骤；
- 已检索证据引用；
- Tool Call 引用及状态；
- 用户确认的任务约束；
- 当前未完成事项；
- 预算消耗；
- 恢复所需的最小变量。

Task Memory 不允许写入用户长期记忆，除非未来版本有明确用户授权和治理规则。

## 7. Checkpoint 与 Memory 的关系

- Checkpoint 是可恢复执行状态，不是面向用户的长期记忆。
- Summary 是面向上下文压缩的摘要，不足以单独恢复执行。
- Task Memory 是任务语义状态，Checkpoint 是 Runtime 执行恢复状态。
- Conversation Message 是原始交互记录。
- 这些对象可以引用彼此，但不能互相替代。

恢复时校验：
- Run 状态是否允许恢复；
- Checkpoint Schema Version；
- Agent Config Version；
- Tool Definition Version；
- 当前用户和服务身份是否仍有效；
- 当前 Policy 是否仍允许继续执行；
- 预算是否仍有剩余；
- Checkpoint 是否在保留期内。

## 8. 存储模型建议

逻辑实体：
- `conversation_summaries`
- `agent_run_states`
- `agent_checkpoints`
- `agent_task_memory_items`
- `memory_artifacts`（可选统一引用表）
- `memory_deletion_jobs`

每条 Memory 至少包含：
- `memory_id`
- `memory_type`
- `owner_subject_id`
- `conversation_id` / `run_id`
- `content_ref` 或结构化 payload
- `source_refs`
- `schema_version`
- `sensitivity_level`
- `created_at` / `expires_at`
- `deleted_at`

避免将大体积内容直接存入高频查询表；可将内容存储于受控对象存储，并在数据库保存引用与元数据。

## 9. 生命周期与删除

- Conversation 删除策略沿用平台既有规则。
- Run 完成后按策略清理短期状态和 Checkpoint。
- Summary 与原始会话采用一致或更短的保留期限，不得因摘要而延长原始个人数据的保留。
- Memory 删除必须覆盖数据库、对象存储、缓存和可重建索引。
- 删除任务异步执行并记录结果；技术审计记录保留遵循独立审计政策。
- Redis 只存可重建的短期状态，不作为唯一事实来源。

## 10. 隐私与安全

- 记忆默认按用户/会话/Run 隔离。
- 不允许不同用户通过相同缓存 Key 读取彼此记忆。
- 摘要生成模型不能自行决定保留敏感个人属性。
- 用户显式删除会话时，关联摘要和任务记忆按规则同步删除。
- 对高敏感内容设置更严格访问和保留策略。
- Trace 默认只记录摘要和引用，不复制完整 Memory 内容。
- 记忆检索结果仍需进行权限检查。

## 11. API 建议

- `GET /api/v1/conversations/{id}/context-status`
- `POST /api/v1/conversations/{id}/summarize`（内部/受控）
- `GET /api/v1/agent-runs/{run_id}/state`
- `GET /api/v1/agent-runs/{run_id}/checkpoints`（管理员/内部诊断）
- `DELETE /api/v1/conversations/{id}/memory`（纳入用户删除流程）
- `GET /api/v1/agent-runs/{run_id}/budget`

普通用户不应读取 Runtime 原始 State 或内部 Checkpoint 内容。

## 12. 测试与验收

- 超长对话触发摘要且回答质量不明显退化；
- 摘要明确区分事实、推断和待确认项；
- 摘要失败不影响会话可用；
- Token Budget 根据模型能力动态计算；
- Tool Result 裁剪不丢失必要字段；
- Checkpoint 可恢复但不能跨用户/跨 Run 读取；
- 删除会话后关联 Summary/Task Memory/Checkpoint 按策略清理；
- 缓存 Key 包含足够的安全隔离维度；
- 不把 Secret、权限决策或敏感身份注入模型；
- 恢复时重新校验身份和 Policy。

**Exit Criteria：** 单 Agent 能在长对话和多步执行中使用摘要与任务状态；上下文预算可控；Checkpoint 可恢复；记忆有明确访问、保留和删除策略。
