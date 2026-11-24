# V1.0 Mock Tool 契约

- [ToolDefinition](schemas/internal/tool-definition.json) 登记固定版本 `v1` 的 `mock.request_status`、调用权限、低风险等级、幂等语义和单次执行限制。默认禁用。固定输入和结果结构由下列 Schema 描述。
- [ToolInvocation](schemas/internal/tool-invocation.json) 携带服务端 Request ID、Trace ID、工具标识、版本、绝对截止时间和 `sample_id`。当前 `AccessContext`、授权事实和工具启用状态由可信调用方提供。
- [ToolResult](schemas/internal/tool-result.json) 回传原请求关联和工具版本。`SUCCEEDED` 携带结构化状态。`REJECTED` 携带 `ACCESS_DENIED`、`TOOL_UNAVAILABLE`、`DEADLINE_EXCEEDED` 或 `SAMPLE_NOT_FOUND`。

工具用于开发与测试的内部管理调用。执行前经 Policy 核对当前 Admin 身份、环境和 `tool.invoke_mock`，再检查当前定义与截止时间。`sample-001` 返回 `PENDING`，`sample-002` 返回 `COMPLETED`，`sample-003` 用于不存在的样例。数据来自固定内存样本，调用路径涉及的 Schema 均登记为内部制品。

设计草案的 `ToolCallRequest` 和 `ToolCallResult` 分别对应当前 `ToolInvocation` 和 `ToolResult`。Run/Step、外部连接、审批和持久化执行记录按对应版本的 Tool Gateway 任务实施。V1.0 问答侧保留工具意图提示，Mock 契约以独立用例验证。
