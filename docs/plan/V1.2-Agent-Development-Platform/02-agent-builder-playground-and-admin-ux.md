# 02 — Agent Builder、Playground 与 Admin UX 设计

> 公共字段、状态、事件、权限与迁移映射见 [统一契约与跨版本演进规则](../../architecture/统一契约与跨版本演进规则.md)；本文件描述本版能力及增量，具体实现须通过契约与升级验收。

> 版本：V1.2  
> 目标用户：平台管理员、Agent 开发者、业务 Agent Owner、只读审计人员

## 1. 产品目标

V1.2 在既有 Chat + Admin 双入口下扩展 Agent 开发工作台。不要增加第三个一级产品入口。Agent 开发和治理功能归入 Admin；员工使用已发布 Agent 的入口归入 Chat。

### Admin 导航建议

- 仪表盘
- Agent 平台
  - Agent 列表
  - Agent 创建 / 编辑
  - Playground
  - Prompt 管理
  - Agent 评测
  - 发布记录
- 供应商与模型
- 知识库管理
- Tools / Connectors
- 治理与评测
  - Agent Runs / Trace
  - 评测报告
- 权限与人员
- 操作审计日志
- 配置中心

V1.2 应复用 V1.0 Admin 的导航和视觉体系，不改变已确认的两个产品入口。

## 2. Agent 列表页

### 2.1 列表字段

| 字段 | 说明 |
|---|---|
| Agent 名称 | 名称、图标、唯一 Key |
| 描述 | 用途摘要 |
| Owner / Team | 责任人和归属团队 |
| 当前发布版本 | v1、v2 等 |
| 状态 | 草稿、运行中、暂停、归档 |
| 可见范围 | 私有、团队、组织 |
| 最近更新时间 | 最近配置变更 |
| 最近运行 | 最近一次 Run 时间 |
| 操作 | 查看、编辑、复制、测试、发布、归档 |

筛选：名称/Key、状态、Owner、Team、可见范围、更新时间。支持分页、排序、空状态、加载和错误状态。

### 2.2 创建 Agent

采用向导式创建，但允许先创建最小草稿：
1. 基础信息：名称、Key、描述、分类、Owner、可见范围。
2. 运行模板：V1.2 选择平台支持的 Single Agent 模板。
3. 模型：选择有权使用的 Model Profile。
4. Prompt：选择已有 Prompt 或新建。
5. 知识库：选择有权访问的 KB。
6. Tools：从已授权 Tool Catalog 选择。
7. Memory / Context：配置受控选项。
8. 安全策略：输入/输出 Guardrail、审批策略。
9. 保存草稿。

创建过程中每一步都可暂存。默认值应安全、低成本、只读工具优先。

## 3. Agent 编辑器

不做任意 Graph/DAG 编辑器。采用受控表单 + 原始 Definition JSON 只读/高级查看模式。

建议页面分区：
- Overview：基本信息、Owner、状态、版本。
- Instructions：Prompt 绑定、变量、预览。
- Model：Model Profile、温度、输出 Token、调用预算。
- Knowledge：KB 绑定、检索策略、引用要求。
- Tools：Tool 选择、参数限制、读写等级、审批要求。
- Memory & Context：记忆开关、摘要策略、上下文预算。
- Guardrails：输入输出策略、拒答、引用验证。
- Runtime：最大步骤、超时、重试和并发限制。
- Versions：版本历史、差异、发布与回滚。

页面应清晰区分“Agent 默认配置”和“环境配置”。API Key、凭证、生产连接密钥不出现在编辑器中。

## 4. Tool Catalog 与绑定体验

Tool Catalog 展示：
- Tool 名称、描述、所属 Connector
- 输入参数 Schema 和示例
- 只读 / 写入 / 高风险分类
- 需要的权限 Scope
- 当前可用状态、版本、Owner
- Playground 是否支持 Sandbox

绑定 Tool 时展示“此 Agent 将获得可请求的能力范围”，并提示最终权限仍由 Policy Engine 和最终用户身份决定。对写操作显示审批要求；若没有审批策略则禁止绑定到 Production。

## 5. Prompt 管理

Prompt 列表字段：名称、用途、Owner、最新版本、关联 Agent 数、更新时间、状态。

Prompt 详情：
- 模板编辑器
- 变量定义面板（名称、类型、是否必填、默认值、说明）
- 预览输入区
- 渲染结果预览
- 版本历史与 Diff
- 关联 Agent Version 列表
- 测试用例与运行结果

预览必须区分“仅渲染”与“实际模型调用”。实际模型调用需要明确提示成本并使用 Playground 配额。

## 6. Playground

### 6.1 目标

提供开发者隔离调试环境，帮助验证 Prompt、检索、Tool、Memory、上下文和模型配置。Playground 不是生产 Chat 的替代品。

### 6.2 页面布局

左侧：Agent 草稿 / 目标版本选择、模拟身份、环境、测试参数。  
中间：对话调试区、输入框、流式输出、重新运行。  
右侧：运行详情 Tab：
- Plan / Steps（V1.2 单 Agent 执行步骤）
- Tool Calls：请求参数、脱敏响应、耗时、授权决策
- Retrieval：KB、召回文档、引用、检索耗时
- Prompt：模板版本、渲染结果（敏感字段遮蔽）
- Context：历史摘要、Token 预算、裁剪信息
- Model：Model Profile、Token、耗时、成本估算
- Trace：Trace ID、Run ID、错误和事件时间线

### 6.3 调试能力

- 选择 Draft 或已发布版本进行对照测试。
- 设置模拟用户身份，但只能选择授权测试身份或受控测试角色。
- 重置会话、复制 Trace ID、重新执行。
- 展示 Tool 调用前后的 Policy Decision。
- 支持 Mock Tool / Sandbox Connector。
- 支持测试输入变量和预设会话。
- 失败时展示可操作错误，不暴露密钥、内部堆栈或未授权数据。

### 6.4 沙箱约束

- Playground 默认只读和 Mock 工具。
- 禁止直接使用生产写操作。
- 测试身份权限不得高于操作者权限。
- 测试数据与生产会话分离。
- 设置单次 Token、调用次数、最大运行时间和并发配额。
- 所有真实外部调用必须显式授权、单独配额和审计；V1.2 默认不开放。

## 7. Evaluation 工作台

评测页面分为：
1. Dataset：数据集、版本、样本、标签、期望答案/断言。
2. Run：选择 Agent Version、Dataset Version、评测配置。
3. Results：逐样本输入、输出、引用、Tool Trace、评分和失败原因。
4. Compare：不同 Agent Version / Prompt Version 的指标差异。
5. Gate：发布门禁规则和阈值。
6. Reports：评测报告和导出（按角色授权）。

发布门禁至少支持：
- 必测样本完成率
- 任务成功率
- 回答质量 / Groundedness
- Citation Validity
- Tool 成功率
- 越权调用次数必须为 0
- P95 延迟与 Token 成本预算
- 严重安全用例通过率

评分阈值由项目基线配置，不应在代码中散落硬编码。V1.2 至少一种语义评分方式及适用的 RAGAS Adapter 为 P0，确定性断言负责安全/引用/参数门禁；额外 Judge 和校准可列 P1。必选评分器失败或缺分时显示未完成并阻断对应 Gate，不能默认为通过。

## 8. 发布中心

发布流程 UI：
1. 选择目标 Agent 草稿版本。
2. 显示变更摘要与 Diff。
3. 执行配置验证。
4. 运行必需评测。
5. 展示 Gate 结果。
6. 发布确认（高影响变更可要求二次确认或审批）。
7. 生成发布记录。
8. 支持回滚至历史版本。

发布页面必须明确显示：当前生产版本、候选版本、差异、评测报告、发布人、发布时间和回滚目标。

## 9. Chat 端 Agent 使用体验

员工只看到已发布且对其可见的 Agent：
- Agent 目录或默认 Agent 入口
- Agent 名称、用途和数据范围提示
- 新建会话、历史会话
- 每条回答可复制 Trace ID（沿用 V1.0 规则）
- 不展示开发者 Prompt、内部 Tool 参数、敏感 Trace
- Agent 暂停或无权限时给出清晰提示

员工不得选择 Draft，不得通过请求参数指定未授权 Agent Version。

## 10. 角色与权限矩阵建议

| 能力 | 超级管理员 | Agent 开发者 | Agent Owner | 只读审计员 | 普通员工 |
|---|---:|---:|---:|---:|---:|
| 查看组织 Agent | 是 | 按授权 | 按授权 | 元数据/匿名 Trace | 已发布可见 Agent |
| 创建 Agent | 是 | 按授权 | 否/按授权 | 否 | 否 |
| 编辑草稿 | 是 | 按授权 | 自有 Agent | 否 | 否 |
| Playground | 是 | 按授权 | 自有 Agent | 否 | 否 |
| 运行评测 | 是 | 按授权 | 自有 Agent | 查看报告 | 否 |
| 发布 | 是 | 按发布权限 | 默认否 | 否 | 否 |
| 回滚/暂停/恢复 | Policy + operate | 显式 operate 授权 | 默认仅申请；授权后可操作 | 否 | 否 |
| 查看敏感 Trace | 高危授权流程 | 脱敏 | 脱敏 | 匿名 | 否 |

具体角色应纳入既有 RBAC；后端按统一契约第 7 节执行动作→Policy Action→资源 Permission 映射。发布使用 publish，回滚/暂停/恢复使用 operate，Owner 不默认拥有二者。UI 与 API 采用同一矩阵，不能只隐藏按钮。

## 11. 可用性与无障碍

- 表单支持自动保存草稿和离开提醒。
- 长任务评测显示进度、可取消、失败可重试。
- 所有列表支持空态、加载态、错误态。
- 运行事件流断线后可通过 Run ID 恢复查询。
- 表单错误定位到字段，提供错误码。
- 关键动作（发布、回滚、暂停、归档）确认并显示影响范围。

## 12. UX 验收标准

1. 开发者可在 Admin 完成创建 Agent 的完整流程。
2. 可编辑 Prompt、模型、KB、Tools、Memory、Context 和 Guardrail 配置。
3. Playground 可运行并展示主要 Trace 细节。
4. Playground 的生产写操作默认阻断。
5. 可创建 Dataset、执行评测并查看逐样本结果。
6. 发布页面能显示 Gate 结果并阻止不达标发布。
7. 已发布 Agent 能在 Chat 中按权限展示和使用。
8. 普通员工无法访问 Admin 开发功能和 Draft Agent。
9. 页面权限与后端 API 权限一致。
