// @vitest-environment node
import { createServer } from 'node:http';
import { afterAll, beforeAll, beforeEach, expect, it } from 'vitest';
import { createApiClient } from './index';

let status = 200;
let payload: object = { status: 'ok' };
let rawBody: string | undefined;
let correlationHeaders: Record<string, string> = {};
let baseUrl = '';
const server = createServer((request, response) => {
  response.writeHead(request.url === '/health/live' ? status : 404, {
    'Content-Type': 'application/json',
    ...correlationHeaders,
  });
  response.end(rawBody ?? JSON.stringify(payload));
});

beforeAll(async () => {
  await new Promise<void>((resolve) => server.listen(0, '127.0.0.1', resolve));
  const address = server.address();
  if (address === null || typeof address === 'string')
    throw new Error('Server address is unavailable');
  baseUrl = `http://127.0.0.1:${address.port}`;
});

beforeEach(() => {
  status = 200;
  payload = { status: 'ok' };
  rawBody = undefined;
  correlationHeaders = {};
});

afterAll(async () => {
  await new Promise<void>((resolve, reject) =>
    server.close((error) => (error ? reject(error) : resolve())),
  );
});

it('uses the process liveness endpoint and validates its response', async () => {
  await expect(createApiClient(baseUrl).getLiveness()).resolves.toEqual({
    status: 'ok',
  });
});

it('reports unsuccessful HTTP responses without leaking their payload', async () => {
  status = 503;
  payload = { internal: 'private diagnostic' };
  await expect(createApiClient(baseUrl).getLiveness()).rejects.toMatchObject({
    status: 503,
    message: 'HTTP request failed (503)',
  });
});

it('rejects an unexpected response instead of asserting its type', async () => {
  payload = { status: 'unavailable' };
  await expect(createApiClient(baseUrl).getLiveness()).rejects.toThrow(
    'Invalid liveness response',
  );
});

it('propagates caller cancellation', async () => {
  const controller = new AbortController();
  controller.abort();
  await expect(
    createApiClient(baseUrl).getLiveness(controller.signal),
  ).rejects.toMatchObject({ name: 'AbortError' });
});

it('reads a validated public error and its correlation metadata', async () => {
  status = 422;
  payload = {
    error: {
      code: 'API_VALIDATION_ERROR',
      message: '请求参数不合法',
      request_id: '12345678-1234-4321-8123-123456789abc',
      retryable: false,
      details: { error_count: 1 },
    },
  };
  correlationHeaders = { 'X-Trace-ID': '1234567890abcdef1234567890abcdef' };
  await expect(createApiClient(baseUrl).getLiveness()).rejects.toMatchObject({
    status: 422,
    code: 'API_VALIDATION_ERROR',
    message: '请求参数不合法',
    requestId: '12345678-1234-4321-8123-123456789abc',
    traceId: '1234567890abcdef1234567890abcdef',
    retryable: false,
    details: { error_count: 1 },
  });
});

it('rejects malformed error envelopes without displaying their message', async () => {
  status = 500;
  payload = {
    error: {
      code: 'INTERNAL_ERROR',
      message: 'private diagnostic',
      request_id: 'not-a-uuid',
      retryable: false,
      details: {},
    },
  };
  await expect(createApiClient(baseUrl).getLiveness()).rejects.toMatchObject({
    status: 500,
    message: 'HTTP request failed (500)',
    code: undefined,
    requestId: undefined,
  });
});

it('handles non-JSON HTTP errors using safe headers and a status fallback', async () => {
  status = 503;
  rawBody = '<html>private upstream diagnostic</html>';
  correlationHeaders = {
    'X-Request-ID': '12345678-1234-4321-8123-123456789abc',
    'X-Trace-ID': 'invalid-trace',
  };
  await expect(createApiClient(baseUrl).getLiveness()).rejects.toMatchObject({
    status: 503,
    message: 'HTTP request failed (503)',
    requestId: '12345678-1234-4321-8123-123456789abc',
    traceId: undefined,
    retryable: false,
  });
});
