// @vitest-environment node
import { createServer } from 'node:http';
import { afterAll, beforeAll, beforeEach, expect, it } from 'vitest';
import { createApiClient } from './index';

let status = 200;
let payload: object = { status: 'ok' };
let baseUrl = '';
const server = createServer((request, response) => {
  response.writeHead(request.url === '/health/live' ? status : 404, {
    'Content-Type': 'application/json',
  });
  response.end(JSON.stringify(payload));
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
