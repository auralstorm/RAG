# 06｜V1.1 完整研发实施计划与阶段验收标准

> 公共字段、状态、事件、权限与迁移映射见 [统一契约与跨版本演进规则](../../architecture/统一契约与跨版本演进规则.md)；本文件描述本版能力及增量，具体实现须通过契约与升级验收。

**项目：** Enterprise Agentic AI Platform  
**文档版本：** V1.1  
**状态：** 研发执行基线（待启动会确认人员、周期和容量目标）  
**适用范围：** Agent Platform Foundation  
**规划基准：** 建议 6 个阶段；阶段 Exit Criteria 优先于日历日期

---

## 1. 文档目的

将 V1.1 的架构和设计转化为可执行研发计划，明确：
- 阶段目标、依赖和 Exit Criteria；
- Backend、AI/Agent、Frontend、QA、Platform 的任务边界；
- 逐项开发任务、交付物和验收标准；
- 安全、可靠性、可观测性和性能门禁；
- V1.0 升级兼容要求。

本版本以 V1.0 已交付系统为基础，不重新建设 V1.0 的知识库、文档入库、Standard RAG、Model Gateway 和基础权限功能。

## 2. 版本范围冻结

### 2.1 Must Have
- 单 Agent Runtime（LangGraph Adapter）；
- Agent Run/Step 状态和事件；
- Checkpoint、恢复、取消和超时；
- Tool Gateway 和 Tool Contract；
- Mock Connector；
- REST/SQL/MCP Adapter 的 Contract 或骨架（按 POC 决定本版本完成到何种可运行程度）；
- Policy 扩展到 agent.run、tool.invoke、connector.use；
- 基础 Memory/Context、Summary、Task Memory、Token Budget；
- Agent Trace；
- 并发、限流、预算和 Worker 隔离；
- Chat 最小 Agent 使用入口；
- 测试、文档、部署和迁移。

### 2.2 Should Have
- REST Adapter 的受控只读实现；
- SQL Adapter 的参数化只读模板；
- MCP Adapter 的受信 Server 接入骨架；
- Admin Runtime 聚合监控。

### 2.3 Out of Scope
- Agent Builder/Playground 完整产品化；
- Agent Registry 可视化管理和发布回滚中心；
- Planner / Task Decomposition；
- Multi-Agent；
- 完整长期 User Memory；
- Workflow Engine；
- 真实企业系统生产写操作；
- 任意代码、Shell、URL 或 SQL 执行。

## 3. 角色与责任

| 角色 | 主要责任 |
|---|---|
| Tech Lead / Architect | 版本范围、模块边界、ADR、Contract 评审 |
| Backend Lead | Agent/Tool/Policy API、数据模型、业务服务 |
| Agent Engineer | LangGraph Adapter、Graph、State、Checkpoint |
| Integration Engineer | Connector Adapter、Mock/REST/SQL/MCP |
| Frontend Engineer | Chat Agent 入口、Run 状态与错误体验 |
| QA / Security QA | 状态机、权限、注入、幂等、恢复和回归 |
| Platform / SRE | Worker、队列、部署、监控、压测和故障演练 |
| Product Owner | 场景、交互和版本验收 |

## 4. 阶段总览

| 阶段 | 主题 | 主要交付 |
|---|---|---|
| M0 | 启动、V1.0 基线检查与 POC | 版本范围、技术验证、ADR、Contract 冻结 |
| M1 | Agent Domain 与 Runtime 基础 | Run/Step、LangGraph Adapter、Agent Worker |
| M2 | Tool Gateway 与 Mock Connector | Tool Contract、Policy、Schema、幂等、Mock |
| M3 | Checkpoint、Memory 与 Context | 恢复、取消、摘要、Task Memory、Budget |
| M4 | Chat 集成、Trace 与治理 | Agent Chat、事件流、Trace、审计、并发控制 |
| M5 | 集成测试、压测、安全与发布 | 回归、恢复演练、验收报告、部署手册 |

阶段可以部分并行，但依赖和安全门禁不能跳过。

## 5. M0：启动、基线检查与 POC

### 目标
确认 V1.0 系统可作为 V1.1 基线，验证 LangGraph、Worker、Checkpoint、Tool Contract 和 Policy 调用路径。

### 任务

**M0-01 V1.0 基线检查**
- 检查 V1.0 API、DB Migration、Model Gateway、Retriever API、Policy、Audit、Trace；
- 建立 V1.0 回归用例和测试环境；
- 检查模块边界是否满足 Runtime 接入。
- 验收：V1.0 核心回归通过；遗留问题分级并指定负责人。

**M0-02 LangGraph POC**
- 实现最小 Graph；
- 调用 Model Gateway；
- 使用可控 Mock Tool；
- 验证 State 序列化和中断恢复。
- 验收：POC 证明 Runtime Adapter 可在不暴露框架对象的情况下运行。

**M0-03 Tool Contract POC**
- 定义 JSON Schema；
- 验证 Tool Gateway 到 Mock Adapter 的调用；
- 验证 Policy Deny 在执行前拦截。
- 验收：无权调用不触达 Mock Connector。

**M0-04 Worker 与 Checkpoint POC**
- 验证 Agent Worker 独立队列；
- 验证重复消息、Worker 重启和租约过期。
- 验收：重复消息不会重复执行；恢复行为符合状态机。

**M0-05 ADR 与范围冻结**
- 记录 Checkpoint 存储、同步/异步阈值、事件 Schema 和 Adapter 方案；
- 冻结 Must/Should/Out of Scope。
- 验收：关键 ADR 有决策人、证据和回滚策略。

### 阶段 Exit Criteria
- V1.0 回归通过；
- 核心 POC 可运行；
- 无未解决的高危架构阻塞；
- V1.1 Contract 和范围冻结。

## 6. M1：Agent Domain 与 Runtime 基础

### 目标
交付可以持久化、执行和观察的单 Agent Runtime。

### 任务

**M1-01 Agent Definition**
- 建立受控 Agent Definition；
- 配置 Agent Key、模型、指令、Tool Allowlist、Retriever、预算；
- 支持配置版本。
- 验收：禁用 Agent 不可运行；Run 绑定不可变配置版本。

**M1-02 Agent Run/Step Domain**
- 建立 Run/Step 状态机；
- 实现状态迁移校验；
- 建立统一错误码。
- 验收：非法迁移拒绝；终态不可继续执行。

**M1-03 LangGraph Adapter**
- Graph Factory；
- Model Node、Retriever Node、Tool Dispatch Node；
- Event Adapter。
- 验收：Agent 端到端调用 Model Gateway 和 Retriever API；不直连 ES。

**M1-04 Agent Worker**
- 独立队列；
- Worker 心跳和租约；
- 重复任务幂等；
- Worker 资源隔离。
- 验收：Worker 重启后 Run 可恢复或明确失败；不影响 Ingestion Worker。

**M1-05 Run API**
- 创建 Run；
- 查询 Run；
- 查询 Steps；
- 状态事件 SSE。
- 验收：用户只能查询有权访问的 Run；SSE 可断线重连或回查。

### 阶段 Exit Criteria
- 单 Agent 可运行；
- Run/Step 状态和事件完整；
- 模型和检索走平台 Gateway/Contract；
- Worker 幂等和基础故障恢复通过。

## 7. M2：Tool Gateway 与 Mock Connector

### 目标
实现 Agent 安全调用工具的统一入口。

### 任务

**M2-01 Tool Definition/Version**
- 定义输入输出 Schema、风险等级、Effect、超时和重试策略；
- 建立版本化。
- 验收：无效 Schema 和未声明字段拒绝。

**M2-02 Tool Registry**
- 注册平台 Mock Tool；
- 获取 Agent 允许的 Tool 列表；
- 验证 Tool Version。
- 验收：未注册或未绑定 Tool 不可执行。

**M2-03 Tool Gateway Pipeline**
- Schema Validation；
- Policy Check；
- Budget/Rate Limit；
- Dispatch；
- Output Validation/Redaction。
- 验收：Policy Deny 不调用 Connector；所有调用有 Tool Call 记录。

**M2-04 Mock Connector**
- 员工查询、目录搜索、工单读取等 Mock Tool；
- 注入成功、超时、拒绝、格式错误等测试场景。
- 验收：测试结果稳定可复现，Mock 数据显式标识。

**M2-05 Idempotency**
- 幂等键、唯一约束、重复请求处理；
- UNKNOWN 结果状态。
- 验收：相同幂等请求不会重复执行；超时不盲目重试。

**M2-06 Adapter Skeleton**
- 建立 REST/SQL/MCP Adapter Interface；
- 完成至少一个 Adapter 的受控 POC；
- 其他 Adapter 提供 Contract 和安全约束。
- 验收：任一 Adapter 都不能绕过 Tool Gateway Policy。

### 阶段 Exit Criteria
- Agent 经 Tool Gateway 调用 Mock Tool；
- 参数校验、权限、限流、审计和 Trace 全链路生效；
- 生产写操作仍被禁用；
- Adapter 扩展不破坏 Tool Contract。

## 8. M3：Checkpoint、Memory 与 Context

### 目标
使 Agent 在长对话和中断场景下可控地使用上下文，并具备恢复能力。

### 任务

**M3-01 Checkpoint Adapter**
- 保存/读取 Checkpoint；
- Schema Version；
- TTL 和删除；
- 不保存 Secret。
- 验收：中断后可恢复；版本不兼容时安全暂停。

**M3-02 Recovery Scheduler**
- 识别租约过期 Run；
- 防止多个 Worker 同时恢复；
- 恢复前校验身份、Policy 和 Config Version。
- 验收：恢复任务互斥；已撤销权限的 Run 不继续调用 Tool。

**M3-03 Cancellation**
- 用户取消请求；
- Worker 取消传播；
- 下游请求取消；
- 状态落库。
- 验收：取消后不启动新步骤，终态正确。

**M3-04 Token Budget**
- 读取模型上下文能力；
- 输入/输出预算；
- 超限裁剪顺序。
- 验收：不会无控制突破上下文窗口；关键指令不被静默截断。

**M3-05 Summary Memory**
- 摘要 Schema；
- 异步摘要；
- 事实/推断/待确认区分；
- 原始消息引用。
- 验收：摘要失败不影响对话；删除会话时关联摘要清理。

**M3-06 Task Memory**
- 保存当前 Run 任务事实和引用；
- 与 Checkpoint 分离。
- 验收：跨步骤状态可恢复；不同 Run 数据隔离。

### 阶段 Exit Criteria
- Run 可中断、恢复和取消；
- Token Budget 生效；
- Summary/Task Memory 有清晰语义和生命周期；
- 权限撤销后恢复执行会重新校验。

## 9. M4：Chat、Trace 与治理集成

### 目标
将 Runtime 能力接入统一 Chat，并完成可观察和运维治理。

### 任务

**M4-01 Chat Agent Entry**
- 选择固定 Agent；
- 提交 Run；
- 展示执行状态、步骤摘要和最终回答；
- 显示 TraceId。
- 验收：Standard RAG 仍按原路由工作；Agent 错误有清晰反馈。

**M4-02 Run Event UX**
- SSE 实时事件；
- 断线恢复；
- 取消按钮和等待状态。
- 验收：前端状态与服务端状态一致；重复事件不造成 UI 重复。

**M4-03 Agent Trace**
- Run、Step、Model、Retriever、Tool Span；
- Token、延迟、错误码；
- 配置版本。
- 验收：可从 Trace 定位慢节点和失败 Tool；敏感内容已脱敏。

**M4-04 Audit**
- Tool/Connector 管理变更；
- Policy 变更；
- 高风险操作。
- 验收：关键变更有操作者、对象、结果和前后差异；无普通删除入口。

**M4-05 Concurrency & Budget**
- Agent 并发池；
- 用户/Agent/Tool 限流；
- Step/Token/时间预算；
- 队列积压监控。
- 验收：超限请求被明确拒绝或排队；Worker 不被单个 Agent 耗尽。

### 阶段 Exit Criteria
- Chat Agent 端到端可用；
- Trace/Audit 完整；
- 并发与预算限制可验证；
- V1.0 Chat/RAG 功能无回归。

## 10. M5：集成、安全、压测与发布

### 目标
完成版本级验收和生产发布准备。

### 测试矩阵

| 测试域 | 必测场景 |
|---|---|
| 功能 | Agent Run、Tool Call、Summary、Checkpoint、Cancel |
| 权限 | 无权运行 Agent、读取他人 Run、调用未绑定 Tool |
| 安全 | Prompt Injection、参数注入、Secret 泄露、SSRF 边界 |
| 可靠性 | Worker Crash、重复消息、租约过期、队列积压 |
| 兼容 | V1.0 API/RAG/Chat/DB Migration 回归 |
| 性能 | 并发 Run、慢 Tool、模型限流、队列吞吐 |
| 生命周期 | 会话删除、Summary/Checkpoint 清理、TTL |
| 可观测 | Trace 关联、错误码、告警和仪表盘 |

### M5-01 全量回归
- 运行 V1.0 回归；
- 运行 V1.1 单元、集成和 Contract 测试。
- 验收：关键路径通过率达到项目门槛，P0/P1 缺陷关闭或书面接受。

### M5-02 安全验收
- 权限负向测试；
- Tool 越权；
- Secret/PII 泄露；
- Prompt Injection；
- SSRF/SQL Injection 边界。
- 验收：不存在可绕过 Policy 的调用路径。

### M5-03 故障恢复演练
- Kill Agent Worker；
- 重复投递消息；
- 模型供应商超时；
- Tool 超时；
- Redis 不可用；
- Checkpoint Schema 不兼容。
- 验收：Run 状态最终一致；无重复副作用；恢复失败有明确告警。

### M5-04 压测
指标至少包括：
- Agent Run 并发数；
- Run 接受延迟；
- Queue Wait；
- Agent 执行耗时；
- 模型/Tool 调用延迟；
- Worker CPU/Memory；
- 失败率、重试率；
- Token/Run；
- 队列积压和恢复时间。

具体数值由目标环境和业务规模确定，POC 前不预设虚假 SLA。

### M5-05 发布准备
- DB Migration；
- 环境变量和 Secret；
- Worker 部署；
- 队列/Dead Letter；
- Dashboard/Alert；
- 回滚方案；
- Runbook。
- 验收：从 V1.0 环境可升级，失败可回滚应用；数据库迁移有验证和恢复步骤。

## 11. 全局非功能验收

### 安全
- 所有 Tool Call 都经过 Policy；
- Runtime 不能伪造或提升用户权限；
- Secret 不进入 Prompt、日志和 Trace；
- Agent 无法直接访问外部系统；
- 用户不能查看其他用户 Run/Memory。

### 可靠性
- Run 状态持久化；
- 重复消息幂等；
- Worker 崩溃可检测；
- 超时/取消/重试有边界；
- Checkpoint 可验证恢复。

### 可观测
- 每个 Run 有 Trace ID；
- 每个 Tool Call 可追踪；
- 模型、检索、工具耗时分段可见；
- 错误码可聚合；
- 不泄露敏感信息。

### 可维护
- Contract 有版本；
- Adapter 可替换；
- 框架对象不外泄；
- 测试可在 CI 执行；
- 文档与部署配置同步更新。

## 12. 发布准入与退出

发布前必须：
- V1.0 回归通过；
- V1.1 Exit Criteria 全部通过；
- 无未处理的严重安全问题；
- 迁移、部署、回滚和恢复演练完成；
- 运行 Trace 和告警可用；
- 已知限制与风险有负责人。

发布后观察：
- Agent Run 成功率；
- Tool Deny/Failure；
- 模型调用失败率；
- 平均/分位延迟；
- Token/Run；
- Worker 利用率；
- Queue Lag；
- Checkpoint 恢复成功率；
- 用户取消率。

## 13. V1.1 版本完成定义

V1.1 完成意味着平台已经具备可治理的单 Agent 执行底座：Agent 可以在可信身份、Policy、预算和审计约束下调用 RAG 与 Mock Tools；Run 可观察、可取消、可恢复；上下文和状态有清晰生命周期。

这不意味着平台已经具备 V1.2 的可视化 Agent 开发平台，也不意味着可以执行真实企业业务写操作。

## 14. 补充阶段验收

M0 冻结统一契约的公共 Run 状态、幂等唯一键、Definition→Registry 映射及最小 ApprovalRequest/Decision；实施前生成 Schema/OpenAPI 并与实际迁移核对。M2 使用 Mock 验证审批回调的参数绑定、拒绝/过期/重放；M5 保留升级后的配置版本和 Checkpoint TTL，核验旧入口与新入口使用同一授权及状态事实源。部署范围按已确认 ADR-0013 执行。
