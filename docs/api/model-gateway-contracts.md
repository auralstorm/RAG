# V1.0 Provider、ModelConfig 与模型网关契约

日期：2026-11-24。对应 P0-04-05。交付注册元数据、私有引用、Chat/Embedding/Rerank 请求与结果、用量、错误、流事件和纯规则。真实 Provider CRUD、Secret 加密/解析、LiteLLM、Tokenizer、限流/并发和模型调用按 P2/POC-04 验收；本轮没有安装 SDK、写入业务表或调用付费模型。

## 存量与兼容

本轮前没有实际 Provider/ModelConfig/ModelRequest/Response、业务端点或模型表迁移，已有 EmbeddingBinding 是知识/检索消费者使用的稳定模型 ID、config_version、dimensions 绑定。此绑定保持兼容；注册的 ModelConfig.id 对应其 embedding_model_id，config_version/dimension 必须明确匹配，不能用其他模型的相同维度替代。

[POC-03 记录](../plan/V1.0-MVP/implementation/P0-03.md) 已确认阿里云百炼作为 POC 测试供应商及候选模型，真实调用尚未验收。它不成为产品默认配置；本轮合成测试没有采用 POC 候选名称或官方默认维度作为产品常量。Facade + LiteLLM 基线继续依据 [ADR-0005 摘要](../plan/V1.0-MVP/04-poc-acceptance-and-adr.md#adr-0005model-gateway-自研-facade--litellm)，未新增供应商 SDK 或改变 Adapter 边界。

| 原设计 | 规范契约与实施映射 |
|---|---|
| providers.api_key_ciphertext / api_key_key_version | SecretReference 固定 secret_id、版本与环境；密文/Key 版本由 P2 私有 Secret 存储显式映射，公开 DTO 不返回密文或引用，不凭文档直接改列 |
| providers.base_url / proxy_config | StoredProvider 私有端点/代理引用，不接受端点内用户名、密码、Query 或 Fragment；真实网络准入和 DNS/代理/重定向约束由 Adapter/平台配置验证 |
| models.model_key | StoredModelConfig.vendor_model_key 保留供应商路由标识，公开 ModelConfig 用稳定 ID/展示名/配置版本；不将供应商 Key/原始路由名暴露到回答、日志或前端 |
| models.embedding_dimension / capabilities | 维度与 embedding 能力同时存在，Streaming/Tool Calling/JSON Mode 依赖 Chat；Token、批量与能力按实际注册配置校验 |
| 模型默认项、权重、限流 | ModelConfig 元数据保留 is_default、weight、rpm/tpm/max_concurrency；唯一默认配置、实际限流/并发和选择规则在 P2 验收，未实现 V2.0 动态路由或预算账本 |
| config / Token / retry 无类型字典 | 请求按 operation 判别，配置版本必填，TokenMeasurement 绑定请求摘要与 Tokenizer 版本，重试保留原意图与总尝试上限 |

所有对象采用独立字符串 schema_version="1.0"，未知版本与额外字段拒绝；标识为 UUID，时间归一 UTC。公共/内部 DTO 在同一 [模型模块](../../backend/app/modules/model_gateway/domain/contracts.py) 明确分开，未来 API 仍必须显式投影公开字段，不能直接序列化 StoredProvider/StoredModelConfig。没有存量 ID 改写或 DDL/数据迁移。

## Provider 与固定模型配置

Provider 公开 id/name/provider_type/config_version/status/has_credential/时间；StoredProvider 才包含 base_url、可空 credential_ref、proxy_ref 与 timeout_seconds。SecretReference 仅为不透明版本/环境引用，不证明凭据存在、被解密或已获准使用；无引用或环境不符拒绝调用。has_credential 只是引用配置指示，不显示真实 Key 尾号/长度。

ModelConfig 固定稳定模型 ID、Provider ID、配置版本、展示名、ACTIVE/DISABLED、能力集合、Tokenizer 与输入/输出/上下文/批量限制、可空速率/并发值和默认/权重元数据。Chat 必须有 context_window/max_output_tokens；Embedding 必须有明确维度；Embedding/Reranker 必须有批量上限。上下文与参数是注册配置，不推断市场默认值；provider_type 只是平台注册的 Adapter Key，实际是否支持由工厂/集成验证，字符串合法不表示供应商已接入。

capabilities_verified、endpoint_approved 与 admission_allowed 是可信运行事实的必填输入，不由客户端自报，也不代表本轮真实模型、网络或 Redis 门禁已经验证。实际配置发布必须保证版本快照不可变；修改供应商路由、端点、凭据绑定或能力产生受控新版本。Provider 禁用使模型调用拒绝，不必重写所有模型状态；删除依赖、默认模型唯一性与审计按 P2 事务验收。

## 请求、输出与固定向量空间

ModelRequest 公共业务字段仅在后端模块之间传递：request_id/trace_id、model_id/config_version、deadline_at 与 operation 对应载荷。不能携带 api_key/base_url/vendor_model_key/credential_ref 或可自授授权字段；Trace 为服务端非零 32 位十六进制 ID。所有真实调用仍必须经 ModelGateway，框架和 SDK 对象不得进入这些契约。

| operation | 请求与结果规则 |
|---|---|
| chat | 非空文本 messages，system/user/assistant 角色，max_output_tokens、有限温度 [0,2]、stream、text/json_object；结果有 content 与 stop/length/content_filter，空内容仅允许显式 content_filter；完成的 JSON 模式必须是有效对象且拒绝 NaN/Infinity |
| embedding | 非空 texts、query/document 输入用途和完整 EmbeddingBinding；结果每个输入恰有一个零基 index，维度一致、数值有限且向量非零；结果可按 index 重排，不忽略缺失/重复项目 |
| rerank | query、非空候选 documents、top_n；结果 index 唯一且在候选范围内、数量匹配，按分数降序/同分 index 升序排序；分数不是答案正确率 |

本轮仅定义文本 Chat/JSON、Embedding/Rerank；tool_call 是 Registry 能力标签，不表示调用工具已授权，也未实现工具消息/调用 payload、Agent 自动执行或多模态请求。Adapter 不能静默丢失请求参数；不支持的供应商能力或参数映射为稳定拒绝。

ModelResponse 固定 request_id/trace_id、模型 ID/配置、判别输出、ModelUsage 和 elapsed_ms；响应形状校验不等于主体授权。输出 token_count 如已知不能超过请求输出上限。Embedding 的 model/config/dimension 绑定始终匹配既有 IndexVersion/RetrievalIndexBinding；本轮没有自动 Fallback，生产重试/降级不能以相同维度推断可切换向量空间。

## 当前授权、Token 与重试

[调用规则](../../backend/app/modules/model_gateway/application/invocation.py) 复用 [Policy 当前身份校验](../../backend/app/modules/policy/application/authorization.py)，核对用户/身份、目的、环境、伪名与 Policy 版本/有效期。该共享校验本身不授予操作或资源权限，既有 kb.read/manage 行为保持；模型访问还要求从当前可信服务端策略加载 allowed_model_ids/allowed_operations。角色标签、Prompt、客户端、MQ 头和旧允许快照都不能自行构造这些事实。模型内容中知识/会话资源的 ACL 由对应业务用例重新校验，Model Gateway 的模型许可不能替代 KB 权限。

prepare_model_call 检查当前模型/Provider、私有引用环境、准入、固定配置/能力，以及 TokenMeasurement 的请求 SHA-256 与 Tokenizer 版本。Embedding 每个输入有计量，其他操作为完整编码请求计量；输入上限、Chat 输入+输出上下文、批量与维度不满足即拒绝。真实 Tokenizer 负责包含角色/协议包装开销，不能由文本长度、客户端 Token 数或测试固定值冒充计量。

PreparedModelCall 只返回内部执行意图与原摘要/版本、attempt/max_attempts、prepared_at、timeout_seconds；超时不超过 Provider 配置、请求 Deadline 或当前身份/授权有效期剩余时间。它不解析 Secret、不创建连接、不获取真实并发槽或发送请求；真实执行层拥有准入令牌、生命周期、请求/响应及必要持久计量。

prepare_model_retry 仅接受明确可重试、已知 transient 错误；当前流式输出已开始、未知外部结果、预算耗尽或时间倒退拒绝。每次重新加载授权/准入和固定注册事实，保留请求 ID/正文/参数/Deadline/模型版本与 Provider 版本；总尝试上限采用原上限与当前上限的较小值，不因配置放宽而重置。模型生成重试可能再次计费，不宣称供应商按 request_id 免费去重；实际退避、限流、取消/超时结果回查与 Attempt 持久化在 P2 验收。

validate_model_result 在交付前重新检查当前主体和模型权限/固定配置，身份停用、模型撤权/禁用、过期或版本变化拒绝；结果验证不再获取第二个速率/并发槽。流式执行者同样负责在输出期间检查当前权限，并释放客户端断连的资源，不能凭最初许可持续输出已撤权内容。

## 用量、错误与流事件

ModelUsage 区分 REPORTED/ESTIMATED/UNAVAILABLE。缺失 Token 保留 null，不填零；三项已知时 total=input+output，部分已知不能大于 total。ModelCost 独立使用非负 Decimal、货币与 REPORTED/ESTIMATED 来源，不把 Token 估计和供应商确认成本混为一项。失败可能仍有用量，ModelFailure 可携带安全 ModelUsage；没有 V2.0 Reservation/Ledger 或绝对费用上限实现。

ModelFailure 只有稳定 ModelErrorCode、retryable/outcome_unknown 与可空用量，不接受原始供应商消息、HTTP 响应或凭据。默认拒绝对参数/权限/认证/配置/能力/无效结果/Deadline/未知结果重放；已知 UNAVAILABLE/RATE_LIMITED 才可标记 retryable，仍受原尝试上限、Deadline、当前准入和流状态限制。未知副作用必须保留 outcome_unknown，不将本地超时或取消当作供应商未执行。

ModelStreamEvent 为一个尝试的 delta/completed/failed，绑定请求/Trace/模型版本与从 1 起连续 sequence_no，且只含对应载荷。validate_model_stream 检查顺序、关联、唯一终态、结束后的拒绝和完成响应与累积文本一致；允许显式检查未完成前缀，不能把缺终态当成功。completed/failed 与内容过滤/长度结束保持各自事实。事件序号不代表持久化 SSE 恢复协议，本轮不宣称自动续流。

## 制品与后续验收

公共 models 分组导出 Provider、ModelConfig、ModelUsage/Cost/Failure；Secret、私有 Provider/Model、完整请求/响应/流事件、TokenMeasurement/授权事实与执行计划仅生成内部 Schema，不进入前端或实际 OpenAPI。`make contracts` / `make contracts-check` 同步源码与制品，JSON Schema 的类型校验不替代当前权限、Token/引用/结果与重试纯规则。

真实 Secret 加密/轮换/解析、Provider 管理权限、LiteLLM SDK、百炼模型能力/维度/用量、限流并发、流式取消、重试计量、网络约束和日志脱敏必须有 P2/POC-04 证据。本轮测试使用合成事实与固定 Token 数，不能将它们记为真实调用、Crypto 验收或独立安全评审通过；完整 P0-04/M0 仍未关闭。
