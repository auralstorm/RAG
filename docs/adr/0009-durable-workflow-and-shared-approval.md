---
status: proposed
date: 2026-11-23
---

# ADR-0009：确定性 Workflow 使用现有可靠任务底座并复用审批身份

V1.4 需要跨天等待、业务审批、外部写操作确认及补偿。设计选择 PostgreSQL 保存流程/步骤/定时器/操作事实，RabbitMQ + Celery 执行有界任务，Outbox 与周期扫描恢复未派发任务；相较让 LangGraph 承担企业规则或直接引入新的流程引擎，这保持既有技术基线，但平台须实现并验证调度、租约和恢复协议。

Workflow Instance 与 Agent Run 分离；Tool Gateway 和 Policy Engine 作为同一业务执行边界。Approval Center 扩展原 human_interactions 与 ApprovalRequest/ApprovalDecision，通过明确的执行域关联 Agent 或 Workflow，保留 approval_id/decision_id，新增分配和审批阶段记录而不另造平行审批事实。

这些是 [V1.4 开发包](../plan/V1.4-Enterprise-Workflow-and-Integration/README.md) 的设计选择，正式实施前需完成可靠调度、长等待、跨版本迁移及外部幂等 POC，并由架构负责人评审接受。若现有底座无法满足已确认的业务需求，再通过新 ADR 评估外部 Workflow Engine；本草案不代表 POC 已通过。

用户已确认单企业部署及“工单创建→审批→结果确认”的流程类型。具体工单系统、接口能力、审批人和时限由实施计划 M0 的业务/接口冻结清单确定；不从示例推导真实生产授权。
