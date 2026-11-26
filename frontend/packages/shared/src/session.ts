// UI state supplied by the owning app; this is not an authentication token or DTO.
export type SessionState =
  | { readonly status: 'checking' }
  | { readonly status: 'anonymous'; readonly reason?: 'expired' }
  | {
      readonly status: 'authenticated';
      readonly subjectId: string;
      readonly canAccessApplication: boolean;
      readonly authorization: {
        readonly policyVersion: string;
        readonly permissionCodes: readonly string[];
      };
    }
  | { readonly status: 'forbidden' }
  | { readonly status: 'error'; readonly requestId?: string };

export const UNCONNECTED_SESSION: SessionState = { status: 'anonymous' };

export interface SessionCredentials {
  readonly username: string;
  readonly password: string;
}

export interface SessionActions {
  readonly mode: 'local' | 'platform' | 'unavailable';
  readonly login?: (
    credentials: SessionCredentials,
    signal: AbortSignal,
  ) => Promise<void>;
  readonly logout?: () => Promise<void>;
  readonly revalidate?: () => Promise<void>;
}
