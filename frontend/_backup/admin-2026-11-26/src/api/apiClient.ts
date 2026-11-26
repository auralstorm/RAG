import { createApiClient } from '@enterprise-rag/api-client';

export const apiClient = createApiClient(
  new URL(
    import.meta.env.VITE_API_BASE_URL || '/backend/',
    window.location.origin,
  ).href,
);
