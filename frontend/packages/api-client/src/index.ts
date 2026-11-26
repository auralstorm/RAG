import type { components as ChatComponents } from './generated/chat';
import type { components as CommonComponents } from './generated/common';
import type { components as IamComponents } from './generated/iam';
import type { components as KnowledgeComponents } from './generated/knowledge';
import type { components as ModelComponents } from './generated/models';
import type { components as ObservabilityComponents } from './generated/observability';
import type { components as ApiComponents } from './generated/openapi';
import type { components as RetrievalComponents } from './generated/retrieval';
export { createSessionStore } from './session-store';
export type AuthSessionResponse =
  ApiComponents['schemas']['AuthSessionResponse'];
export type LoginCredentials = ApiComponents['schemas']['LoginCredentials'];
export type AuthConfiguration = ApiComponents['schemas']['AuthConfiguration'];
export type CapabilityView = ApiComponents['schemas']['CapabilityView'];
export type KnowledgeScope = ApiComponents['schemas']['KnowledgeScope'];
export type RoleView = ApiComponents['schemas']['RoleView'];
export type GrantView = ApiComponents['schemas']['GrantView'];
export type ConfirmedMutation = ApiComponents['schemas']['ConfirmedMutation'];
export type CreateRole = ApiComponents['schemas']['CreateRole'];
export type UpdateRole = ApiComponents['schemas']['UpdateRole'];
export type AssignRoles = ApiComponents['schemas']['AssignRoles'];
export type PutGrant = ApiComponents['schemas']['PutGrant'];
export type AuditLogView = ApiComponents['schemas']['AuditLogView'];
export type ProviderAdminView = ApiComponents['schemas']['ProviderAdminView'];
export type CreateProvider = ApiComponents['schemas']['CreateProvider'];
export type UpdateProvider = ApiComponents['schemas']['UpdateProvider'];
export type ProviderMutation = Pick<
  CreateProvider,
  'expected_policy_version' | 'confirm'
>;
export type ProviderVersionMutation =
  ApiComponents['schemas']['ProviderVersionMutation'];
export type ProviderPageResponse =
  ApiComponents['schemas']['ProviderPageResponse'];

export type {
  paths as ApiPaths,
  operations as ApiOperations,
} from './generated/openapi';
export type LivenessResponse = ApiComponents['schemas']['LivenessResponse'];
export type ApiError = ApiComponents['schemas']['ApiError'];
export type ApiErrorEnvelope = ApiComponents['schemas']['ApiErrorEnvelope'];
export type PaginationQuery = CommonComponents['schemas']['PaginationQuery'];
export type User = IamComponents['schemas']['User'];
export type Role = IamComponents['schemas']['Role'];
export type Permission = IamComponents['schemas']['Permission'];
export type UserRole = IamComponents['schemas']['UserRole'];
export type RolePermission = IamComponents['schemas']['RolePermission'];
export type SystemRoleCode = IamComponents['schemas']['SystemRoleCode'];
export type ResourceGrant = IamComponents['schemas']['ResourceGrant'];
export type KnowledgeBase = KnowledgeComponents['schemas']['KnowledgeBase'];
export type EmbeddingBinding =
  KnowledgeComponents['schemas']['EmbeddingBinding'];
export type KnowledgeDocument = KnowledgeComponents['schemas']['Document'];
export type DocumentVersion = KnowledgeComponents['schemas']['DocumentVersion'];
export type DocumentVersionRef =
  KnowledgeComponents['schemas']['DocumentVersionRef'];
export type IngestionJob = KnowledgeComponents['schemas']['IngestionJob'];
export type IngestionEvent = KnowledgeComponents['schemas']['IngestionEvent'];
export type IngestionFailure =
  KnowledgeComponents['schemas']['IngestionFailure'];
export type IngestionProgress =
  KnowledgeComponents['schemas']['IngestionProgress'];
export type IndexVersion = KnowledgeComponents['schemas']['IndexVersion'];
export type IndexPublication =
  KnowledgeComponents['schemas']['IndexPublication'];
export type RetrievalSelection =
  RetrievalComponents['schemas']['RetrievalSelection'];
export type RetrievalFilters =
  RetrievalComponents['schemas']['RetrievalFilters'];
export type RetrievalResult = RetrievalComponents['schemas']['RetrievalResult'];
export type RetrievedChunk = RetrievalComponents['schemas']['RetrievedChunk'];
export type RetrievalDiagnostics =
  RetrievalComponents['schemas']['RetrievalDiagnostics'];
export type ChunkSource = RetrievalComponents['schemas']['ChunkSource'];
export type ChunkSourceSpan = RetrievalComponents['schemas']['ChunkSourceSpan'];
export type ChunkMetadata = RetrievalComponents['schemas']['ChunkMetadata'];
export type ScoreComponents = RetrievalComponents['schemas']['ScoreComponents'];
export type ModelProvider = ModelComponents['schemas']['Provider'];
export type ModelConfig = ModelComponents['schemas']['ModelConfig'];
export type ModelUsage = ModelComponents['schemas']['ModelUsage'];
export type ModelCost = ModelComponents['schemas']['ModelCost'];
export type ModelFailure = ModelComponents['schemas']['ModelFailure'];
export type Conversation = ChatComponents['schemas']['Conversation'];
export type Message = ChatComponents['schemas']['Message'];
export type Citation = ChatComponents['schemas']['Citation'];
export type Trace = ObservabilityComponents['schemas']['Trace'];
export type TraceSpan = ObservabilityComponents['schemas']['TraceSpan'];
export type AuditEvent = ObservabilityComponents['schemas']['AuditEvent'];
export type PageResponse<Item> = Omit<
  CommonComponents['schemas']['PageResponse'],
  'items'
> & { readonly items: readonly Item[] };

const uuidPattern =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function isProviderAdminView(value: unknown): value is ProviderAdminView {
  if (!isRecord(value)) return false;
  const allowed = [
    'schema_version',
    'id',
    'name',
    'provider_type',
    'config_version',
    'status',
    'has_credential',
    'created_at',
    'updated_at',
    'base_url',
    'timeout_seconds',
    'proxy_configured',
    'remarks',
  ];
  if (Object.keys(value).some((key) => !allowed.includes(key))) return false;
  if (
    value.schema_version !== '1.0' ||
    typeof value.id !== 'string' ||
    !uuidPattern.test(value.id) ||
    typeof value.name !== 'string' ||
    !value.name.trim() ||
    value.name.length > 128 ||
    typeof value.provider_type !== 'string' ||
    !/^[a-z][a-z0-9_]{0,63}$/.test(value.provider_type) ||
    typeof value.config_version !== 'string' ||
    !value.config_version.trim() ||
    value.config_version.length > 128 ||
    (value.status !== 'ACTIVE' && value.status !== 'DISABLED') ||
    typeof value.has_credential !== 'boolean' ||
    typeof value.created_at !== 'string' ||
    !Number.isFinite(Date.parse(value.created_at)) ||
    typeof value.updated_at !== 'string' ||
    !Number.isFinite(Date.parse(value.updated_at)) ||
    typeof value.base_url !== 'string' ||
    typeof value.timeout_seconds !== 'number' ||
    !Number.isSafeInteger(value.timeout_seconds) ||
    value.timeout_seconds < 1 ||
    value.timeout_seconds > 300 ||
    typeof value.proxy_configured !== 'boolean' ||
    typeof value.remarks !== 'string' ||
    value.remarks.length > 1000
  )
    return false;
  try {
    const endpoint = new URL(value.base_url);
    return (
      ['http:', 'https:'].includes(endpoint.protocol) &&
      !endpoint.username &&
      !endpoint.password &&
      !endpoint.search &&
      !endpoint.hash
    );
  } catch {
    return false;
  }
}

function providerPage(
  payload: unknown,
  page: number,
  pageSize: number,
): ProviderPageResponse {
  if (
    !isRecord(payload) ||
    !Array.isArray(payload.items) ||
    typeof payload.total !== 'number' ||
    !Number.isSafeInteger(payload.total) ||
    payload.total < 0 ||
    payload.page !== page ||
    payload.page_size !== pageSize ||
    payload.items.length > pageSize ||
    payload.items.length > payload.total ||
    !payload.items.every(isProviderAdminView)
  )
    throw new Error('Invalid provider list response');
  return {
    items: payload.items,
    total: payload.total,
    page,
    page_size: pageSize,
  };
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
  if (
    !['http:', 'https:'].includes(origin.protocol) ||
    origin.username ||
    origin.password
  ) {
    throw new Error('Invalid API base URL');
  }
  origin.search = '';
  origin.hash = '';
  if (!origin.pathname.endsWith('/')) origin.pathname += '/';

  async function privateRequest(
    path: string,
    init: RequestInit = {},
  ): Promise<Response> {
    const response = await fetcher(new URL(`api/v1/${path}`, origin), {
      ...init,
      credentials: 'include',
      cache: 'no-store',
      signal: init.signal
        ? AbortSignal.any([init.signal, AbortSignal.timeout(10_000)])
        : AbortSignal.timeout(10_000),
    });
    if (!response.ok) throw await responseError(response);
    return response;
  }

  function authRequest(
    operation: string,
    application: 'chat' | 'admin',
    init: RequestInit = {},
  ) {
    return privateRequest(`auth/${application}/${operation}`, init);
  }

  async function adminCsrf(signal?: AbortSignal): Promise<string> {
    const payload: unknown = await (
      await authRequest('csrf', 'admin', signal ? { signal } : {})
    ).json();
    if (
      !isRecord(payload) ||
      typeof payload.csrf_token !== 'string' ||
      !/^[0-9a-f]{64}$/.test(payload.csrf_token)
    )
      throw new Error('Invalid CSRF response');
    return payload.csrf_token;
  }

  async function providerMutation(
    method: 'POST' | 'PATCH' | 'DELETE',
    path: string,
    payload: ProviderMutation | CreateProvider | UpdateProvider,
    signal?: AbortSignal,
  ): Promise<Response> {
    const csrf = await adminCsrf(signal);
    return privateRequest(`admin/providers${path}`, {
      method,
      ...(signal ? { signal } : {}),
      headers: {
        'Content-Type': 'application/json',
        'X-CSRF-Token': csrf,
      },
      body: JSON.stringify(payload),
    });
  }

  async function sessionResponse(
    response: Response,
    application: 'chat' | 'admin',
  ): Promise<AuthSessionResponse> {
    const payload: unknown = await response.json();
    if (!isRecord(payload) || !isRecord(payload.user))
      throw new Error('Invalid session response');
    const user = payload.user;
    if (
      payload.application !== application ||
      typeof payload.csrf_token !== 'string' ||
      !/^[0-9a-f]{64}$/.test(payload.csrf_token) ||
      typeof payload.expires_at !== 'string' ||
      !Number.isFinite(Date.parse(payload.expires_at)) ||
      typeof user.id !== 'string' ||
      !uuidPattern.test(user.id) ||
      user.schema_version !== '1.0' ||
      typeof user.display_name !== 'string' ||
      !user.display_name.trim() ||
      user.display_name.length > 128 ||
      user.status !== 'ACTIVE' ||
      typeof user.created_at !== 'string' ||
      !Number.isFinite(Date.parse(user.created_at)) ||
      typeof user.updated_at !== 'string' ||
      !Number.isFinite(Date.parse(user.updated_at))
    ) {
      throw new Error('Invalid session response');
    }
    return {
      application,
      csrf_token: payload.csrf_token,
      expires_at: payload.expires_at,
      user: {
        id: user.id,
        schema_version: '1.0',
        display_name: user.display_name,
        status: user.status,
        created_at: user.created_at,
        updated_at: user.updated_at,
      },
    };
  }

  return {
    authorization: {
      async capabilities(
        application: 'chat' | 'admin',
        subjectId: string,
        signal: AbortSignal,
      ): Promise<CapabilityView> {
        const payload: unknown = await (
          await privateRequest(`authorization/${application}/me`, { signal })
        ).json();
        const codes = (value: unknown): value is string[] =>
          Array.isArray(value) &&
          value.length <= 1000 &&
          value.every(
            (code: unknown) =>
              typeof code === 'string' &&
              code.length <= 128 &&
              /^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$/.test(code),
          ) &&
          new Set(value).size === value.length;
        if (
          !isRecord(payload) ||
          Object.keys(payload).some(
            (key) =>
              ![
                'subject_id',
                'application',
                'policy_version',
                'permission_codes',
                'roles',
              ].includes(key),
          ) ||
          payload.application !== application ||
          typeof payload.subject_id !== 'string' ||
          !uuidPattern.test(payload.subject_id) ||
          payload.subject_id.toLowerCase() !== subjectId.toLowerCase() ||
          typeof payload.policy_version !== 'string' ||
          !/^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$/.test(payload.policy_version) ||
          !codes(payload.permission_codes) ||
          !Array.isArray(payload.roles) ||
          payload.roles.length > 1000
        )
          throw new Error('Invalid capability response');
        const roles = payload.roles.map((role: unknown): Role => {
          if (
            !isRecord(role) ||
            Object.keys(role).some(
              (key) =>
                ![
                  'id',
                  'schema_version',
                  'code',
                  'name',
                  'is_system',
                  'protected',
                ].includes(key),
            ) ||
            role.schema_version !== '1.0' ||
            typeof role.id !== 'string' ||
            !uuidPattern.test(role.id) ||
            typeof role.code !== 'string' ||
            !/^[A-Z][A-Z0-9_]{0,63}$/.test(role.code) ||
            typeof role.name !== 'string' ||
            !role.name.trim() ||
            role.name.length > 128 ||
            typeof role.is_system !== 'boolean' ||
            typeof role.protected !== 'boolean'
          )
            throw new Error('Invalid capability response');
          const system = ['SUPER_ADMIN', 'KB_ADMIN', 'AUDIT_READONLY'].includes(
            role.code,
          );
          if (system ? !role.is_system || !role.protected : role.is_system)
            throw new Error('Invalid capability response');
          return {
            id: role.id,
            schema_version: '1.0',
            code: role.code,
            name: role.name,
            is_system: role.is_system,
            protected: role.protected,
          };
        });
        return {
          subject_id: payload.subject_id,
          application,
          policy_version: payload.policy_version,
          permission_codes: payload.permission_codes,
          roles,
        };
      },
    },
    auth: {
      async configuration(
        application: 'chat' | 'admin',
        signal: AbortSignal,
      ): Promise<AuthConfiguration> {
        const payload: unknown = await (
          await authRequest('config', application, { signal })
        ).json();
        if (
          !isRecord(payload) ||
          (payload.mode !== 'local' &&
            payload.mode !== 'platform' &&
            payload.mode !== 'unavailable')
        )
          throw new Error('Invalid auth configuration');
        return { mode: payload.mode };
      },
      async login(
        application: 'chat' | 'admin',
        credentials: LoginCredentials,
        signal: AbortSignal,
      ) {
        return sessionResponse(
          await authRequest('login', application, {
            method: 'POST',
            signal,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(credentials),
          }),
          application,
        );
      },
      async me(application: 'chat' | 'admin', signal: AbortSignal) {
        return sessionResponse(
          await authRequest('me', application, { signal }),
          application,
        );
      },
      async csrf(
        application: 'chat' | 'admin',
        signal: AbortSignal,
      ): Promise<string> {
        const payload: unknown = await (
          await authRequest('csrf', application, { signal })
        ).json();
        if (
          !isRecord(payload) ||
          typeof payload.csrf_token !== 'string' ||
          !/^[0-9a-f]{64}$/.test(payload.csrf_token)
        )
          throw new Error('Invalid CSRF response');
        return payload.csrf_token;
      },
      async refresh(
        application: 'chat' | 'admin',
        csrf: string,
        signal: AbortSignal,
      ) {
        return sessionResponse(
          await authRequest('refresh', application, {
            method: 'POST',
            signal,
            headers: { 'X-CSRF-Token': csrf },
          }),
          application,
        );
      },
      async logout(
        application: 'chat' | 'admin',
        csrf: string,
        signal: AbortSignal,
      ): Promise<void> {
        await authRequest('logout', application, {
          method: 'POST',
          signal,
          headers: { 'X-CSRF-Token': csrf },
        });
      },
    },
    providers: {
      async list(
        query: {
          readonly page: number;
          readonly page_size: number;
          readonly name?: string;
          readonly provider_type?: string;
          readonly status?: 'ACTIVE' | 'DISABLED';
        },
        signal?: AbortSignal,
      ): Promise<ProviderPageResponse> {
        const parameters = new URLSearchParams({
          page: String(query.page),
          page_size: String(query.page_size),
        });
        if (query.name) parameters.set('name', query.name);
        if (query.provider_type)
          parameters.set('provider_type', query.provider_type);
        if (query.status) parameters.set('status', query.status);
        const payload: unknown = await (
          await privateRequest(
            `admin/providers?${parameters.toString()}`,
            signal ? { signal } : {},
          )
        ).json();
        return providerPage(payload, query.page, query.page_size);
      },
      async get(id: string, signal?: AbortSignal): Promise<ProviderAdminView> {
        if (!uuidPattern.test(id)) throw new Error('Invalid provider ID');
        const payload: unknown = await (
          await privateRequest(
            `admin/providers/${id}`,
            signal ? { signal } : {},
          )
        ).json();
        if (!isProviderAdminView(payload))
          throw new Error('Invalid provider response');
        return payload;
      },
      async create(
        payload: CreateProvider,
        signal?: AbortSignal,
      ): Promise<ProviderAdminView> {
        const result = await providerMutation('POST', '', payload, signal);
        const body: unknown = await result.json();
        if (!isProviderAdminView(body))
          throw new Error('Invalid provider response');
        return body;
      },
      async update(
        id: string,
        payload: UpdateProvider,
        signal?: AbortSignal,
      ): Promise<ProviderAdminView> {
        if (!uuidPattern.test(id)) throw new Error('Invalid provider ID');
        const result = await providerMutation(
          'PATCH',
          `/${id}`,
          payload,
          signal,
        );
        const body: unknown = await result.json();
        if (!isProviderAdminView(body))
          throw new Error('Invalid provider response');
        return body;
      },
      async delete(
        id: string,
        payload: ProviderVersionMutation,
        signal?: AbortSignal,
      ): Promise<void> {
        if (!uuidPattern.test(id)) throw new Error('Invalid provider ID');
        await providerMutation('DELETE', `/${id}`, payload, signal);
      },
    },
    async getLiveness(signal?: AbortSignal): Promise<LivenessResponse> {
      const response = await fetcher(
        new URL('health/live', origin),
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
