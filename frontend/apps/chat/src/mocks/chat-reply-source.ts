import type { ChatReplySource } from '../features/chat/types';
import { getMockAnswer } from './chat-answers';

function waitForChunk(signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    signal.throwIfAborted();
    const timer = setTimeout(() => {
      signal.removeEventListener('abort', handleAbort);
      resolve();
    }, 70);
    function handleAbort() {
      clearTimeout(timer);
      reject(signal.reason);
    }
    signal.addEventListener('abort', handleAbort, { once: true });
  });
}

export const mockReplySource: ChatReplySource = {
  notice: '开发环境 · 回答为模拟内容',
  async *streamReply(question, signal) {
    const answer = Array.from(getMockAnswer(question));
    for (let position = 0; position < answer.length; position += 12) {
      await waitForChunk(signal);
      signal.throwIfAborted();
      yield answer.slice(position, position + 12).join('');
    }
  },
};
