# 可执行 HTTP 契约制品

当前交付 P0-04 的公共 HTTP 契约。后端 DTO 与真实路由是生成来源，JSON/OpenAPI/TypeScript 文件为生成制品；修改源定义后运行 `make contracts`，使用 `make contracts-check` 检查一致性，该检查已纳入 `make check` 和现有 CI 入口。

| 制品 | 来源与用途 |
|---|---|
| [openapi.json](openapi.json) | [实际 FastAPI 应用](../../backend/app/main.py) 的 OpenAPI 3.1，当前业务路由尚未实现，只包含实际健康检查接口及公共错误组件 |
| [API Error Schema](schemas/api-error.json) | [公共 DTO](../../backend/app/api/schemas/common.py) 的 `ApiErrorEnvelope`，固定 `error.code/message/request_id/retryable/details` |
| [分页参数 Schema](schemas/pagination-query.json) | `PaginationQuery`，页码从 1 起、默认 1；page_size 默认 20、范围 1–100；未知字段拒绝 |
| [分页响应 Schema](schemas/page-response.json) | `PageResponse`，包含 `items/total/page/page_size`；total 非负，返回数量不得超过 page_size 或 total |
| [HTTP TypeScript 类型](../../frontend/packages/api-client/src/generated/openapi.ts) | 从实际 OpenAPI 生成，在公共 api-client 导出并供 Chat/Admin 消费 |
| [分页 TypeScript 类型](../../frontend/packages/api-client/src/generated/common.ts) | 从独立 JSON Schema 生成；公共客户端只替换泛型 items 类型，其余字段来自生成制品 |

[生成脚本](../../scripts/contracts.py) 固定非私有应用元数据、不启动服务或访问数据库；[私有构建工具](../../frontend/packages/api-codegen/package.json) 使用 `openapi-typescript==7.13.0` 与其支持的 TypeScript `5.9.3`，应用及客户端类型检查继续使用既有 TypeScript `6.0.3`。构建工具不作为应用运行依赖，也不创建业务 API 占位路由。生成输入仅来自仓库内制品，不抓取远程 Schema。

## HTTP 错误与关联信息

标准 HTTP 异常按状态映射为 [公开错误摘要](../../backend/app/api/errors.py)，保留 WWW-Authenticate、Retry-After、Allow 等协议头；异常原始 detail 不进入响应。参数校验错误仅暴露 error_count，不返回原始输入、任意字典键或 Pydantic 异常全文。未知异常返回 HTTP 500、`INTERNAL_ERROR`、retryable=false，并记录关联 ID 与异常类型的摘要。

[请求中间件](../../backend/app/api/middleware/request_context.py) 为每个 HTTP 请求生成新的 Request ID，不采纳客户端自报的 X-Request-ID。返回 X-Request-ID、X-Trace-ID、traceparent；有效的 W3C version-00 traceparent 仅用于关联，生成新的 span_id。缺失、重复、格式错误或全零父上下文产生新的 Trace ID；它不是身份、授权或真实 Span 导出的证明。

允许的 Chat/Admin Origin 可读取这些响应头，也可提交 traceparent。请求/流体不被中间件缓存；响应开始后的异常终止流并以安全异常摘要退出，不追加第二个 JSON 响应。客户端校验 Error Envelope 后提供 code、公开 message、requestId、traceId、retryable 和 details；非 JSON 或格式错误的响应使用 HTTP 状态摘要，取消与 I/O 错误继续传播。

retryable 不自动触发重试，写入重放仍取决于身份、原 Idempotency-Key、当前状态和实际副作用。健康检查的既有响应继续使用自身契约：live 返回 `status=ok`，ready 的 200/503 返回 ReadinessReport；CORS preflight 由 Starlette 的 CORS 协议处理。

分页默认值和上限是当前 HTTP 输入约束，不是业务容量、文档规模或并发 SLO。真实列表接口仍需从可信身份与资源范围查询 items/total，并在数据库模块验收分页/排序/过滤行为。

## 主线后续

完整 P0-04 的身份、ACL、文档/索引状态、解析/检索、Model Gateway、消息/引用、Trace/Audit 等模型和模块契约继续按 [P0-04 进度](../plan/V1.0-MVP/implementation/P0-04.md) 交付。数据库 DDL/迁移、OIDC 登录、完整 Trace 传播和独立评审尚未完成，不从本目录生成制品推断对应业务能力已经实现。
