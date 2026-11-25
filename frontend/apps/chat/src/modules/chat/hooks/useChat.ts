import { useEffect, useRef, useState } from 'react';
import type { ChatReplySource, ChatSession, ChatTurn } from '../chat.types';

const EMPTY_SESSION: ChatSession = {
  id: 'initial',
  title: '新对话',
  turns: [],
};

export function useChat(replySource: ChatReplySource | null) {
  const [{ sessions, activeId }, setChat] = useState({
    sessions: [EMPTY_SESSION],
    activeId: EMPTY_SESSION.id,
  });
  const requests = useRef(new Map<string, AbortController>());
  const session =
    sessions.find((item) => item.id === activeId) ??
    sessions[0] ??
    EMPTY_SESSION;
  const running = session.turns.some(
    ({ status }) => status === 'loading' || status === 'updating',
  );

  useEffect(() => {
    const activeRequests = requests.current;
    return () => {
      activeRequests.forEach((request) => request.abort());
      activeRequests.clear();
    };
  }, []);

  function updateTurn(
    sessionId: string,
    turnId: string,
    update: Partial<ChatTurn>,
  ) {
    setChat((current) => ({
      ...current,
      sessions: current.sessions.map((item) =>
        item.id === sessionId
          ? {
              ...item,
              turns: item.turns.map((turn) =>
                turn.id === turnId ? { ...turn, ...update } : turn,
              ),
            }
          : item,
      ),
    }));
  }

  function clearRequest(sessionId: string) {
    requests.current.get(sessionId)?.abort();
    requests.current.delete(sessionId);
  }

  function generate(sessionId: string, turnId: string, question: string) {
    if (!replySource) return;
    const source = replySource;
    const request = new AbortController();
    requests.current.set(sessionId, request);
    async function receiveReply() {
      let answer = '';
      try {
        for await (const delta of source.streamReply(
          question,
          request.signal,
        )) {
          if (requests.current.get(sessionId) !== request) return;
          answer += delta;
          updateTurn(sessionId, turnId, { answer, status: 'updating' });
        }
        if (requests.current.get(sessionId) === request) {
          updateTurn(sessionId, turnId, { answer, status: 'success' });
        }
      } catch {
        if (requests.current.get(sessionId) === request) {
          updateTurn(sessionId, turnId, { status: 'error' });
        }
      } finally {
        if (requests.current.get(sessionId) === request) {
          requests.current.delete(sessionId);
        }
      }
    }
    void receiveReply();
  }

  function newSession() {
    if (session.turns.length === 0) return;
    stop();
    const next = { ...EMPTY_SESSION, id: crypto.randomUUID() };
    setChat((current) => ({
      sessions: [next, ...current.sessions],
      activeId: next.id,
    }));
  }

  function selectSession(sessionId: string) {
    if (sessionId === activeId || !sessions.some(({ id }) => id === sessionId))
      return;
    stop();
    setChat((current) => ({ ...current, activeId: sessionId }));
  }

  function deleteSession(sessionId: string) {
    clearRequest(sessionId);
    const fallback = { ...EMPTY_SESSION, id: crypto.randomUUID() };
    setChat((current) => {
      const remaining = current.sessions.filter(
        (item) => item.id !== sessionId,
      );
      const next = remaining.length > 0 ? remaining : [fallback];
      return {
        sessions: next,
        activeId:
          current.activeId === sessionId
            ? (next[0]?.id ?? fallback.id)
            : current.activeId,
      };
    });
  }

  function renameSession(sessionId: string, title: string) {
    if (!title.trim()) return;
    setChat((current) => ({
      ...current,
      sessions: current.sessions.map((item) =>
        item.id === sessionId ? { ...item, title: title.trim() } : item,
      ),
    }));
  }

  function send(value: string) {
    const question = value.trim();
    if (!replySource || !question || requests.current.has(session.id))
      return false;
    const turn: ChatTurn = {
      id: crypto.randomUUID(),
      question,
      answer: '',
      status: 'loading',
      feedback: null,
    };
    setChat((current) => ({
      ...current,
      sessions: current.sessions.map((item) =>
        item.id === session.id
          ? {
              ...item,
              title: item.turns.length
                ? item.title
                : Array.from(question).slice(0, 32).join(''),
              turns: [...item.turns, turn],
            }
          : item,
      ),
    }));
    generate(session.id, turn.id, question);
    return true;
  }

  function stop() {
    clearRequest(session.id);
    setChat((current) => ({
      ...current,
      sessions: current.sessions.map((item) =>
        item.id === session.id
          ? {
              ...item,
              turns: item.turns.map((turn) =>
                turn.status === 'loading' || turn.status === 'updating'
                  ? { ...turn, status: 'abort' }
                  : turn,
              ),
            }
          : item,
      ),
    }));
  }

  function retry(turn: ChatTurn) {
    if (
      !replySource ||
      requests.current.has(session.id) ||
      !session.turns.some(({ id }) => id === turn.id)
    )
      return;
    updateTurn(session.id, turn.id, {
      answer: '',
      status: 'loading',
      feedback: null,
    });
    generate(session.id, turn.id, turn.question);
  }

  return {
    sessions,
    session,
    running,
    canSend: replySource !== null,
    selectSession,
    newSession,
    deleteSession,
    renameSession,
    send,
    stop,
    retry,
    feedback: (turnId: string, feedback: ChatTurn['feedback']) =>
      updateTurn(session.id, turnId, { feedback }),
  };
}
