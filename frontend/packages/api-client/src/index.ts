import type { components as ApiComponents } from './generated/openapi';
import type { components as CommonComponents } from './generated/common';

export type {
  paths as ApiPaths,
  operations as ApiOperations,
} from './generated/openapi';
export type LivenessResponse = ApiComponents['schemas']['LivenessResponse'];
export type ApiError = ApiComponents['schemas']['ApiError'];
export type ApiErrorEnvelope = ApiComponents['schemas']['ApiErrorEnvelope'];
export type PaginationQuery = CommonComponents['schemas']['PaginationQuery'];
export type PageResponse<Item> = Omit<
  CommonComponents['schemas']['PageResponse'],
  'items'
> & { readonly items: readonly Item[] };

const uuidPattern =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function publicError(payload: unknown): ApiError | undefined {
  if (!isRecord(payload) || !isRecord(payload.error)) return undefined;
  const error = payload.error;
  if (
    typeof error.code !== 'string' ||
    error.code.length > 128 ||
    !/^[A-Z][A-Z0-9_]*$/.test(error.code) ||
    typeof error.message !== 'string' ||
    error.message.length === 0 ||
    error.message.length > 512 ||
    typeof error.request_id !== 'string' ||
    !uuidPattern.test(error.request_id) ||
    typeof error.retryable !== 'boolean' ||
    (error.details !== undefined && !isRecord(error.details))
  ) {
    return undefined;
  }
  return {
    code: error.code,
    message: error.message,
    request_id: error.request_id,
    retryable: error.retryable,
    details: error.details ?? {},
  };
}

async function responseError(response: Response): Promise<HttpError> {
  let payload: unknown;
  try {
    payload = await response.json();
  } catch (error) {
    // Empty/non-JSON errors are safe fallbacks; cancellation and I/O failures still propagate.
    if (!(error instanceof SyntaxError)) throw error;
  }
  return new HttpError(response.status, publicError(payload), response.headers);
}

export class HttpError extends Error {
  readonly status: number;
  readonly code: string | undefined;
  readonly requestId: string | undefined;
  readonly traceId: string | undefined;
  readonly retryable: boolean;
  readonly details: NonNullable<ApiError['details']>;

  constructor(status: number, error?: ApiError, headers?: Headers) {
    super(error?.message ?? `HTTP request failed (${status})`);
    this.name = 'HttpError';
    this.status = status;
    this.code = error?.code;
    const requestId = error?.request_id ?? headers?.get('X-Request-ID');
    this.requestId =
      requestId && uuidPattern.test(requestId) ? requestId : undefined;
    const traceId = headers?.get('X-Trace-ID');
    this.traceId =
      traceId && /^[0-9a-f]{32}$/.test(traceId) ? traceId : undefined;
    this.retryable = error?.retryable ?? false;
    this.details = error?.details ?? {};
  }
}

export function createApiClient(
  baseUrl: string,
  fetcher: typeof fetch = fetch,
) {
  const origin = new URL(baseUrl);

  return {
    async getLiveness(signal?: AbortSignal): Promise<LivenessResponse> {
      const response = await fetcher(
        new URL('/health/live', origin),
        signal ? { signal } : {},
      );
      if (!response.ok) throw await responseError(response);

      const payload: unknown = await response.json();
      if (
        typeof payload !== 'object' ||
        payload === null ||
        !('status' in payload) ||
        payload.status !== 'ok'
      ) {
        throw new Error('Invalid liveness response');
      }
      return { status: payload.status };
    },
  };
}
