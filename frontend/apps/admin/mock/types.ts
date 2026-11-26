/** Mock 中间件请求/响应的宽松类型，对齐 vite-plugins/mockPlugin 适配层 */
export interface MockRequest {
  body: unknown;
  query: Record<string, string>;
  params: Record<string, string>;
}

export interface MockResponse {
  statusCode?: number;
  status(code: number): MockResponse;
  send(payload: unknown): void;
  json(payload: unknown): void;
  setHeader(k: string, v: string): void;
  end(): void;
}
