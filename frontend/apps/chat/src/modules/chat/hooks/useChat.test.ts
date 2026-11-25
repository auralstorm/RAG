import { StrictMode } from 'react';
import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { getMockAnswer } from '../mocks/chatAnswers';
import { MOCK_REPLY_SOURCE } from '../mocks/chatReplySource';
import type { ChatReplySource } from '../chat.types';
import { useChat } from './useChat';

const useTestChat = () => useChat(MOCK_REPLY_SOURCE);

const question = '如何申请 VPN 访问？';

describe('chat state', () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it('disables submission when no reply source is available', () => {
    const { result } = renderHook(() => useChat(null));
    expect(result.current.canSend).toBe(false);
    act(() => expect(result.current.send(question)).toBe(false));
    expect(result.current.session.turns).toEqual([]);
    expect(vi.getTimerCount()).toBe(0);
  });

  it('keeps partial output on a source error and permits a retry', async () => {
    let failed = false;
    const source: ChatReplySource = {
      notice: '',
      async *streamReply() {
        yield 'partial answer';
        if (!failed) {
          failed = true;
          throw new Error('sensitive transport details');
        }
        yield ' complete';
      },
    };
    const { result } = renderHook(() => useChat(source));
    await act(async () => {
      result.current.send(question);
    });
    expect(result.current.session.turns[0]).toMatchObject({
      answer: 'partial answer',
      status: 'error',
    });
    expect(result.current.running).toBe(false);
    const turn = result.current.session.turns[0];
    if (!turn) throw new Error('Expected failed turn');
    await act(async () => {
      result.current.retry(turn);
    });
    expect(result.current.session.turns[0]).toMatchObject({
      answer: 'partial answer complete',
      status: 'success',
    });
    expect(result.current.session.turns).toHaveLength(1);
  });

  it('discards late output even if the reply source ignores cancellation', async () => {
    let deliverChunk: (delta: string) => void = () => {
      throw new Error('Source not started');
    };
    const source: ChatReplySource = {
      notice: '',
      async *streamReply() {
        yield await new Promise<string>((resolve) => {
          deliverChunk = resolve;
        });
      },
    };
    const { result } = renderHook(() => useChat(source));
    act(() => result.current.send(question));
    const firstId = result.current.session.id;
    act(() => result.current.newSession());
    await act(async () => {
      deliverChunk('late output');
    });
    expect(result.current.session.turns).toEqual([]);
    act(() => result.current.selectSession(firstId));
    expect(result.current.session.turns[0]).toMatchObject({
      answer: '',
      status: 'abort',
    });
  });

  it('rejects empty and duplicate submissions, then finishes the full answer', async () => {
    const { result } = renderHook(useTestChat);
    act(() => {
      expect(result.current.send('  ')).toBe(false);
      expect(result.current.send(` ${question} `)).toBe(true);
      expect(result.current.send(question)).toBe(false);
    });
    expect(result.current.session.turns).toHaveLength(1);
    expect(result.current.running).toBe(true);
    await act(() => vi.advanceTimersByTimeAsync(70));
    expect(result.current.session.turns[0]?.status).toBe('updating');
    expect(result.current.session.turns[0]?.answer.length).toBeGreaterThan(0);
    await act(() => vi.runAllTimersAsync());
    expect(result.current.session.turns[0]?.answer).toBe(
      getMockAnswer(question),
    );
    expect(result.current.session.turns[0]?.status).toBe('success');
    expect(result.current.running).toBe(false);
    expect(vi.getTimerCount()).toBe(0);
  });

  it('keeps partial output when stopped and retries the same turn', async () => {
    const { result } = renderHook(useTestChat);
    act(() => result.current.send(question));
    await act(() => vi.advanceTimersByTimeAsync(140));
    const partial = result.current.session.turns[0]?.answer;
    act(() => result.current.stop());
    await act(() => vi.advanceTimersByTimeAsync(1000));
    expect(result.current.session.turns[0]).toMatchObject({
      answer: partial,
      status: 'abort',
    });
    const turn = result.current.session.turns[0];
    if (!turn) throw new Error('Expected the stopped turn');
    act(() => result.current.retry(turn));
    await act(() => vi.runAllTimersAsync());
    expect(result.current.session.turns).toHaveLength(1);
    expect(result.current.session.turns[0]).toMatchObject({
      id: turn.id,
      answer: getMockAnswer(question),
      status: 'success',
    });
  });

  it('stops a request before its first chunk', async () => {
    const { result } = renderHook(useTestChat);
    act(() => {
      result.current.send(question);
      result.current.stop();
    });
    await act(() => vi.runAllTimersAsync());
    expect(result.current.session.turns[0]).toMatchObject({
      answer: '',
      status: 'abort',
    });
    expect(result.current.running).toBe(false);
  });

  it('cancels generation on creation and selection without mixing sessions', async () => {
    const { result } = renderHook(useTestChat);
    const firstId = result.current.session.id;
    act(() => result.current.send(question));
    act(() => result.current.newSession());
    const secondId = result.current.session.id;
    expect(secondId).not.toBe(firstId);
    expect(result.current.session.turns).toEqual([]);
    expect(vi.getTimerCount()).toBe(0);
    act(() => result.current.send('如何提交 IT 工单？'));
    await act(() => vi.advanceTimersByTimeAsync(70));
    const partial = result.current.session.turns[0]?.answer;
    act(() => result.current.selectSession(firstId));
    await act(() => vi.runAllTimersAsync());
    expect(result.current.session.turns[0]).toMatchObject({
      question,
      answer: '',
      status: 'abort',
    });
    act(() => result.current.selectSession(secondId));
    expect(result.current.session.turns[0]).toMatchObject({
      answer: partial,
      status: 'abort',
    });
    act(() => result.current.selectSession('missing'));
    expect(result.current.session.id).toBe(secondId);
  });

  it('atomically deletes multiple sessions and keeps a usable empty session', async () => {
    const { result } = renderHook(useTestChat);
    const firstId = result.current.session.id;
    act(() => result.current.send(question));
    act(() => result.current.newSession());
    const secondId = result.current.session.id;
    act(() => result.current.send(question));
    act(() => {
      result.current.deleteSession(firstId);
      result.current.deleteSession(secondId);
    });
    await act(() => vi.runAllTimersAsync());
    expect(result.current.sessions).toHaveLength(1);
    expect(result.current.session.turns).toEqual([]);
    expect(result.current.session.id).not.toBe(firstId);
    expect(result.current.session.id).not.toBe(secondId);
    expect(vi.getTimerCount()).toBe(0);
    act(() => expect(result.current.send(question)).toBe(true));
    await act(() => vi.runAllTimersAsync());
    expect(result.current.session.turns[0]?.status).toBe('success');
  });

  it('keeps a renamed title through follow-up questions and isolates feedback', async () => {
    const { result } = renderHook(useTestChat);
    act(() => result.current.send(question));
    await act(() => vi.runAllTimersAsync());
    const turn = result.current.session.turns[0];
    if (!turn) throw new Error('Expected the completed turn');
    act(() => {
      result.current.renameSession(result.current.session.id, '  网络支持  ');
      result.current.feedback(turn.id, 'like');
    });
    act(() => result.current.send('如何提交 IT 工单？'));
    await act(() => vi.runAllTimersAsync());
    expect(result.current.session.title).toBe('网络支持');
    expect(result.current.session.turns[0]?.feedback).toBe('like');
    expect(result.current.session.turns[1]?.feedback).toBeNull();
    act(() => result.current.feedback(turn.id, null));
    expect(result.current.session.turns[0]?.feedback).toBeNull();
    act(() => result.current.renameSession(result.current.session.id, '  '));
    expect(result.current.session.title).toBe('网络支持');
  });

  it('rejects retries from another session', async () => {
    const { result } = renderHook(useTestChat);
    act(() => result.current.send(question));
    await act(() => vi.runAllTimersAsync());
    const turn = result.current.session.turns[0];
    if (!turn) throw new Error('Expected a completed turn');
    act(() => result.current.newSession());
    act(() => result.current.retry(turn));
    expect(result.current.session.turns).toEqual([]);
    expect(vi.getTimerCount()).toBe(0);
  });

  it('releases generation timers on unmount under Strict Mode', async () => {
    const { result, unmount } = renderHook(useTestChat, {
      wrapper: StrictMode,
    });
    act(() => result.current.send(question));
    expect(vi.getTimerCount()).toBe(1);
    unmount();
    expect(vi.getTimerCount()).toBe(0);
  });
});
