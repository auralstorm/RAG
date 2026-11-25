import type { ChatReplySource } from '../features/chat/types';

export async function loadReplySource(): Promise<ChatReplySource | null> {
  if (import.meta.env.DEV && import.meta.env.MODE === 'development') {
    const { mockReplySource } = await import('../mocks/chat-reply-source');
    return mockReplySource;
  }
  return null;
}
