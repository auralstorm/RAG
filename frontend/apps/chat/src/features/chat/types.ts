// Feature view models; platform DTOs remain in the generated API client.
export type AnswerStatus =
  'loading' | 'updating' | 'success' | 'abort' | 'error';

export interface ChatTurn {
  readonly id: string;
  readonly question: string;
  readonly answer: string;
  readonly status: AnswerStatus;
  readonly feedback: 'like' | 'dislike' | null;
}

export interface ChatSession {
  readonly id: string;
  readonly title: string;
  readonly turns: readonly ChatTurn[];
}

export interface ChatReplySource {
  readonly notice: string;
  streamReply(question: string, signal: AbortSignal): AsyncIterable<string>;
}
