# Enterprise Agentic AI Platform

本词汇表统一知识问答、Agent 执行、人工介入与评测中的业务术语。字段、接口和迁移规则见《统一契约与跨版本演进规则》。

## Language

**Agent Definition**：Agent 的声明式能力与运行策略描述。受控配置与平台发布定义属于同一概念的不同演进形态。

**Agent Version**：某个 Agent 的不可变配置快照；生命周期元数据与配置内容分开管理。

**Agent Run**：一次用户请求触发的 Agent 执行实例，可以包含多轮计划和多个步骤。
_Avoid_：将 Task、Step 或 Workflow Instance 称为 Run

**Agent Step**：一次 Run 内可独立记录执行结果的动作单元，例如模型调用、检索或工具调用。

**Approval Request**：针对具体业务动作及其参数提出的审批待决事项。

**Approval Decision**：授权审批人对一项审批请求作出的决定；它与业务动作执行结果是不同事实。

**Human Interaction**：执行过程中的人工参与事项，包括审批、澄清、复核和异常处理。
_Avoid_：将所有人工交互都称为企业审批流程

**Evaluation Run**：针对固定对象版本、数据集版本和评分配置执行的一次评测。
_Avoid_：将评测运行与被评测的 Agent Run 混为同一对象

**Golden Dataset**：经业务审阅、用于稳定回归和发布验收的版本化样本集合。

**Workflow Definition**：企业确定性流程的规则描述，包含允许的步骤、分支和完成条件。
_Avoid_：将模型生成的自由计划直接称为企业流程规则

**Workflow Version**：某项流程已发布的不可变规则快照，包含业务步骤及其资源绑定。

**Workflow Instance**：一次业务申请触发的流程执行实例；历史实例固定使用启动时的规则快照。
_Avoid_：与 Agent Run 混用

**Workflow Step**：企业流程中的一个规则化执行单元，例如审批、业务动作、等待事件或结果确认。
_Avoid_：与 Agent Step 混用

**Business Action**：对外部业务系统产生实际效果的一次受控操作；工单申请草稿与外部工单创建是不同事实。

**Compensation**：对已经确认成功的业务动作执行明确的补救操作，可能受到外部系统状态和权限限制。
_Avoid_：将补偿等同于撤销全部历史事实

**Reconciliation**：对提交结果不确定的外部操作核对事实，确定后续继续、补偿或人工处理方式。

**Approval Assignment**：某项审批请求在特定时间分配给审批人的处理责任；调整分配不改变已作出的审批决定。

**Organization**：本企业内部的组织归属范围，包含部门和团队。

**Workspace**：本企业内管理协作成员、资源和环境的工作范围；跨 Workspace 共享需要显式授权。

**Usage Record**：一次实际模型或计量操作的用量事实，带来源和配置版本；失败、重试和取消也可能产生用量。

**Budget Reservation**：操作执行前为其可能消耗保留的额度，确认用量后结算，提交不确定时保持待核对。

**Model Route Policy**：在已授权候选模型中选择满足任务能力、区域、预算和质量约束的版本化规则。

**Recovery Set**：一次可验证恢复所需的业务数据、产物、配置、密钥引用及操作证据的关联集合。

**Side Effect Journal**：用于恢复后核对外部业务操作的独立持久记录，保存原操作标识和提交/确认事实。
