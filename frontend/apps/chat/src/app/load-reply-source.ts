import type { ChatReplySource } from '../features/chat/types';

export async function loadReplySource(
  allowMocks = true,
): Promise<ChatReplySource | null> {
  if (
    allowMocks &&
    import.meta.env.DEV &&
    import.meta.env.MODE === 'development'
  ) {
    const { mockReplySource } = await import('../mocks/chat-reply-source');
    return mockReplySource;
  }
  return null;
}
