// UI state supplied by the owning app; this is not an authentication token or DTO.
export type SessionState =
  | { readonly status: 'checking' }
  | { readonly status: 'anonymous'; readonly reason?: 'expired' }
  | {
      readonly status: 'authenticated';
      readonly subjectId: string;
      readonly canAccessApplication: boolean;
    }
  | { readonly status: 'forbidden' }
  | { readonly status: 'error'; readonly requestId?: string };

export const UNCONNECTED_SESSION: SessionState = { status: 'anonymous' };
