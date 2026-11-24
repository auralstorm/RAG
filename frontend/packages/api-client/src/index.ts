export interface LivenessResponse {
  readonly status: 'ok';
}

export class HttpError extends Error {
  readonly status: number;

  constructor(status: number) {
    super(`HTTP request failed (${status})`);
    this.name = 'HttpError';
    this.status = status;
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
      if (!response.ok) throw new HttpError(response.status);

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
