import type { ChatReplySource } from './chat.types';

export async function loadReplySource(
  allowMocks = true,
): Promise<ChatReplySource | null> {
  if (
    allowMocks &&
    import.meta.env.DEV &&
    import.meta.env.MODE === 'development'
  ) {
    const { MOCK_REPLY_SOURCE } = await import('./mocks/chatReplySource');
    return MOCK_REPLY_SOURCE;
  }
  return null;
}
