# 01 — Agent Registry、定义模型与生命周期详细设计

> 公共字段、状态、事件、权限与迁移映射见 [统一契约与跨版本演进规则](../../architecture/统一契约与跨版本演进规则.md)；本文件描述本版能力及增量，具体实现须通过契约与升级验收。

> 版本：V1.2  
> 产品版本：Agent Development Platform  
> 依赖：V1.0 Standard RAG、V1.1 Agent Runtime / Tool Gateway / Memory / Policy  
> 文档性质：研发设计基线；具体实现以 ADR 和验收结果为准

## 1. 目标与范围

V1.2 的目标是把 V1.1 的“可运行 Agent Runtime”升级为“可管理、可配置、可测试、可发布的 Agent 平台”。开发者应能通过 Admin 创建 Agent、绑定工具和知识库、配置 Prompt 与运行参数、在 Playground 调试、执行评测、发布版本并回滚，而不需要为每个业务 Agent 修改平台核心代码。

本版本不重新实现 LangGraph Runtime，不把 Agent 定义等同于任意 Python 代码，也不允许通过配置绕过 Policy Engine。

### 1.1 本版本交付

- Agent Registry：Agent 注册、查询、归档、权限和生命周期管理。
- Agent Definition：声明式定义 Agent 的身份、指令、模型策略、工具绑定、知识库绑定、Memory 策略、上下文策略和安全策略引用。
- Prompt Management：Prompt 模板、变量、版本、预览、校验和发布绑定。
- Tool Binding：Agent 对已注册 Tool 的显式绑定、参数约束和权限范围。
- Agent Version：不可变版本快照、草稿、验证、发布、停用和回滚。
- Agent Playground：模拟用户身份和会话，调试工具调用、检索、Prompt、上下文及运行轨迹。
- Agent Evaluation：测试集、测试运行、评分、回归比较和发布门禁。
- Agent Access Control：创建、编辑、测试、发布、调用和查看 Trace 的权限控制。
- Admin / Chat 集成：Agent 管理与员工可见 Agent 入口。

### 1.2 明确不做

- 可视化任意 DAG / Graph Builder：不作为 V1.2 必需能力；运行图仍由平台受控模板或代码实现。
- Multi-Agent 协作、Supervisor、动态 Planner：V1.3。
- 完整企业 Workflow、业务审批流编排：V1.4。
- 企业级容量/高可用、灾备与运营治理：V2.0。
- 允许用户提交任意 Python、Shell 或未审核插件并直接执行。
- 让 Agent 自行授予 Tool、知识库或数据访问权限。

## 2. 设计原则

1. **Definition is declarative**：Agent 定义只描述“使用什么能力、按什么策略运行”，不承载任意可执行代码。
2. **Version is immutable**：发布版本不可原地修改；任何修改都产生新版本。
3. **Runtime consumes snapshot**：一次 Agent Run 固定绑定一个已发布版本快照，运行期间不因后台编辑而改变。
4. **Policy is authoritative**：定义中的权限配置是申请范围，不是授权凭证；最终由 Policy Engine 判定。
5. **Draft is not production**：草稿和 Playground 使用隔离执行策略，默认不能访问生产写操作。
6. **Reproducibility**：Run 记录 Agent Version、Prompt Version、Model Profile、Tool Binding Snapshot、KB Version、Policy Decision 和 Evaluation Dataset Version。
7. **Backward compatibility**：Definition Schema 带 schema_version；升级通过迁移器完成，不静默改变历史版本语义。

## 3. 核心领域对象

### 3.1 Agent

Agent 是平台内可被授权、测试和发布的业务智能体实体。

| 字段 | 类型 | 说明 |
|---|---|---|
| id | UUID | 稳定标识 |
| agent_key | string | 单企业部署内唯一的机器标识，沿用稳定唯一约束 |
| name | string | 展示名称 |
| description | text | 用途说明 |
| category | enum | knowledge / assistant / operations / custom |
| owner_user_id | UUID | 平台用户责任人；旧主体经 Identity 映射解析 |
| team_id | UUID nullable | 归属团队 |
| status | enum | draft / active / suspended / archived |
| visibility | enum | private / team / organization |
| current_version_id | UUID nullable | 当前生产可用版本；不指向草稿 |
| created_at / updated_at | timestamp | 时间 |
| archived_at | timestamp nullable | 归档时间 |

Agent 实体与 Agent Version 分离。Agent 本身承载稳定身份和治理元数据，具体运行配置放在版本快照中。规范字段与数据库/API 清单保持一致；已存在消费者的 key/owner_id/current_published_version_id 经显式别名转换保留兼容窗口，实际列改名先走迁移。

### 3.2 Agent Definition

建议采用 JSON Schema 校验的声明式结构：

```json
{
  "schema_version": "1.0",
  "identity": {
    "name": "HR Assistant",
    "description": "回答员工 HR 政策问题"
  },
  "runtime": {
    "template": "single_agent_tool_loop",
    "max_steps": 8,
    "timeout_seconds": 90,
    "max_retries": 1,
    "budget": {
      "max_input_tokens": 24000,
      "max_output_tokens": 1800,
      "max_total_tokens": 60000
    }
  },
  "model": {
    "model_profile_id": "uuid",
    "temperature": 0.2,
    "max_output_tokens": 1800
  },
  "prompt": {
    "prompt_version_id": "uuid"
  },
  "knowledge": [
    {
      "knowledge_base_id": "uuid",
      "retrieval_profile": "default",
      "required": true
    }
  ],
  "tools": [
    {
      "tool_id": "uuid",
      "enabled": true,
      "binding_config": {},
      "allowed_operations": ["read"],
      "approval_policy_id": null
    }
  ],
  "memory": {
    "conversation_memory": true,
    "user_memory": false,
    "task_memory": false,
    "retention_policy_id": "uuid"
  },
  "context": {
    "max_context_tokens": 24000,
    "history_strategy": "summary_then_recent",
    "evidence_budget_tokens": 8000
  },
  "guardrails": {
    "input_policy_id": "uuid",
    "output_policy_id": "uuid",
    "citation_required": true
  }
}
```

以上数值为逻辑示例，按实际模型/场景冻结。字段解释、默认策略及 V1.1 配置转换以统一契约第 3 节为准；正式 JSON Schema 在 Phase 0 生成并验证。V1.1 的代码注册、Tool Registry 和旧快照通过 Adapter/迁移器复用，不复制一套生产定义；迁移失败的配置不自动放宽权限或预算。

### 3.3 Agent Version

Agent Version 是一次配置发布的不可变快照，至少包含：

- definition_json 及 schema_version
- definition_hash
- Prompt 版本引用及渲染后的 Prompt 内容 Hash
- Model Profile 版本快照
- Tool Binding 快照
- Knowledge Base 引用及索引版本策略
- Memory / Context / Guardrail 策略引用
- 发布说明、创建人、创建时间
- 验证结果和评测报告引用

引用外部可变对象时，必须决定采用“固定版本快照”还是“运行时受控解析”。模型供应商密钥等秘密不能复制进快照，只保存安全引用。

### 3.4 Agent Environment

V1.2 至少支持：
- Playground：开发调试环境，使用模拟身份、沙箱工具和受限配额。
- Production：员工正式使用环境，使用真实身份、生产策略和已发布版本。

Staging 可作为后续增强，不应为了环境数量增加不必要复杂度。环境配置与 Agent Definition 分离，避免把 API Key、URL、密钥等环境秘密写入版本。

## 4. 生命周期状态机

Agent 实体状态与不可变配置版本的生命周期分别管理：

```text
Agent:
draft -> active <-> suspended -> archived

Version:
draft -> validating -> ready -> published -> superseded
             |
             v
          rejected
```

- Agent：draft / active / suspended / archived。
- Version：draft / validating / ready / published / superseded / rejected。
- 验证失败使用 rejected；修正生成新草稿。暂停/恢复改变 Agent 状态，归档前检查活跃 Run 与引用，不向 Version 写入 suspended/archived。
- 发布/回滚原子更新当前生产指针及相关生命周期元数据，definition_json 与内容 Hash 不可修改。回滚历史快照前重新校验资源、授权与可用性，已启动 Run 继续固定旧快照。

### 4.1 发布前检查

发布操作必须执行服务端验证，不接受前端“已验证”标记：

1. Definition Schema 校验。
2. Prompt 模板变量完整性、长度与危险模式检查。
3. Model Profile 存在、启用且调用者有权使用。
4. Tool 均存在、启用、版本兼容，参数 Schema 合法。
5. Knowledge Base 存在且 Agent 服务身份拥有授权。
6. Memory、Context、Guardrail 策略有效。
7. 运行预算、超时、最大步数和并发配额合法。
8. 必需 Golden Dataset / Evaluation Gate 达标。
9. 高风险 Tool 必须配置审批或禁止生产绑定。
10. 产生不可变发布快照与审计事件。

发布失败应返回结构化错误列表，指出字段路径、错误码、修复建议；不得部分发布。

### 4.2 发布与回滚

- 发布事务：创建版本快照 → 校验 → 写入发布记录 → 原子更新 Agent 当前版本指针。
- 并发发布采用乐观锁或版本号 CAS，防止覆盖其他人的发布。
- 回滚不是修改旧版本，而是将当前指针切回某个历史可用版本，并生成 agent.version.rolled_back 事件。
- 已启动 Run 始终使用启动时绑定的版本；新 Run 才使用新版本。
- 下线版本前检查活跃 Run、定时任务和引用关系。

## 5. Prompt Management

Prompt 作为独立领域对象管理，不散落在 Agent Definition 的任意文本字段中。

### 5.1 Prompt 结构

- Prompt Template：稳定 ID、名称、用途、Owner。
- Prompt Version：不可变模板正文、变量 Schema、版本号、Hash、变更说明。
- Prompt Binding：Agent Version 到 Prompt Version 的绑定。
- Prompt Preview：输入变量、模拟身份、渲染结果；默认不执行模型调用。
- Prompt Test：可选测试用例、断言与模型输出记录。

模板变量使用明确语法并做白名单校验。禁止将用户输入作为模板代码解释。模板渲染结果必须进行敏感信息和 Prompt Injection 风险检查。

### 5.2 Prompt 版本管理

- 修改已发布 Prompt 时创建新版本。
- Prompt 发布不自动影响既有 Agent Version。
- 只有创建新 Agent Version 并重新绑定后，Prompt 变更才进入生产。
- Prompt diff 应支持文本差异和变量 Schema 差异。
- 记录编辑人、审批人（若配置）、发布时间和关联 Agent。

## 6. Tool Binding 与权限边界

Agent Definition 中 Tool Binding 是“允许 Agent 请求使用的能力清单”，不是权限授予。

每次调用链路：

```text
Agent Runtime
  -> Tool Gateway (Agent ID + Agent Version + User Identity + Run ID)
  -> Policy Engine
  -> Tool Adapter / Connector
  -> Result Sanitizer
  -> Agent Runtime
```

强制规则：
- Runtime 不持有底层业务系统凭证。
- Agent 不能自行拼接任意 Tool 名称；只能调用版本快照中的绑定。
- Tool Gateway 对 Tool ID、操作、参数、用户身份、Agent 身份、资源范围做授权。
- Definition 不能扩大最终用户权限；采用用户权限与 Agent 服务授权的交集或明确的受控委托模型。
- Playground 使用 Mock / Sandbox Tool，禁止默认写入生产系统。
- Tool 输出需要大小限制、敏感字段过滤和不可信内容标记。
- 高风险操作采用独立审批策略；不能仅凭 Prompt 指令确认。

## 7. Agent Registry API（逻辑接口）

| Method | Path | 说明 |
|---|---|---|
| POST | /api/v1/agents | 创建 Agent |
| GET | /api/v1/agents | 分页查询 |
| GET | /api/v1/agents/{id} | Agent 详情 |
| PATCH | /api/v1/agents/{id} | 修改元数据 |
| POST | /api/v1/agents/{id}/archive | 归档 |
| POST | /api/v1/agents/{id}/versions | 创建草稿版本 |
| GET | /api/v1/agents/{id}/versions | 版本列表 |
| GET | /api/v1/agent-versions/{version_id} | 版本详情 |
| POST | /api/v1/agent-versions/{id}/validate | 服务端校验 |
| POST | /api/v1/agent-versions/{id}/publish | 发布 |
| POST | /api/v1/agents/{id}/rollback | 回滚 |
| POST | /api/v1/agents/{id}/suspend | 暂停 |
| POST | /api/v1/agents/{id}/resume | 恢复 |

所有写接口需幂等键、审计、权限检查、并发控制和统一错误结构。回滚/暂停/恢复分别检查 agent.rollback/agent.suspend/agent.resume，资源权限均映射到 operate；operate 不授予编辑、发布或工具调用权，完整矩阵见统一契约第 7 节。

## 8. 安全、审计与可观测性

关键审计事件：
- agent.created / updated / archived
- agent.definition.changed
- agent.version.created / validated / published / rolled_back
- agent.tool_binding.changed
- agent.prompt_binding.changed
- agent.access.changed
- agent.suspended / resumed

审计记录包含操作者、角色、对象、前后版本、变更摘要、请求 ID、时间和结果。秘密值不得进入日志。

Trace 关联维度至少包括 agent_id、agent_version_id、run_id、conversation_id（按隐私策略脱敏）、tool_call_id、prompt_version_id、model_profile_version_id。

## 9. 测试策略

- Schema 单元测试：合法/非法 Definition、边界值、未知字段。
- 生命周期集成测试：草稿、校验、发布、并发发布、回滚、暂停。
- 快照一致性测试：发布后修改草稿不影响运行中 Run。
- 权限测试：越权读写、Tool 绑定越权、跨团队访问。
- Prompt 测试：变量缺失、注入内容、模板渲染、版本隔离。
- 安全测试：密钥泄露、任意 Tool 调用、Sandbox 与 Production 隔离。
- 回归测试：历史 Agent Version 可重放或能明确标注不可重放原因。

## 10. V1.2 验收标准

1. 能创建、编辑、复制、归档 Agent。
2. Definition Schema 有版本号、服务端校验和迁移策略。
3. Agent Version 发布后不可修改，历史版本可查看和回滚。
4. 单次 Run 固定绑定 Agent Version 快照。
5. Prompt、Model Profile、Tool、KB、Memory 策略均可显式绑定。
6. 发布时执行完整校验和评测门禁。
7. Tool 调用始终经过 Tool Gateway 与 Policy Engine。
8. Playground 与 Production 的身份、工具、配额和数据隔离有效。
9. 所有关键变更有审计事件。
10. 无需修改 Runtime 核心代码即可创建至少两个配置型 Agent 示例。
