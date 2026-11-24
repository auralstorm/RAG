import { StrictMode } from 'react';
import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { exampleAnswer } from './demo-content';
import { useDemoChat } from './use-demo-chat';

const question = '如何申请 VPN 访问？';

describe('local demo chat', () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it('rejects empty and duplicate submissions, then finishes the full answer', () => {
    const { result } = renderHook(useDemoChat);
    act(() => {
      expect(result.current.send('  ')).toBe(false);
      expect(result.current.send(` ${question} `)).toBe(true);
      expect(result.current.send(question)).toBe(false);
    });
    expect(result.current.session.turns).toHaveLength(1);
    expect(result.current.running).toBe(true);
    act(() => vi.advanceTimersByTime(70));
    expect(result.current.session.turns[0]?.status).toBe('updating');
    expect(result.current.session.turns[0]?.answer.length).toBeGreaterThan(0);
    act(() => vi.runAllTimers());
    expect(result.current.session.turns[0]?.answer).toBe(
      exampleAnswer(question),
    );
    expect(result.current.session.turns[0]?.status).toBe('success');
    expect(result.current.running).toBe(false);
    expect(vi.getTimerCount()).toBe(0);
  });

  it('keeps partial output when stopped and retries the same turn', () => {
    const { result } = renderHook(useDemoChat);
    act(() => result.current.send(question));
    act(() => vi.advanceTimersByTime(140));
    const partial = result.current.session.turns[0]?.answer;
    act(() => result.current.stop());
    act(() => vi.advanceTimersByTime(1000));
    expect(result.current.session.turns[0]).toMatchObject({
      answer: partial,
      status: 'abort',
    });
    const turn = result.current.session.turns[0];
    if (!turn) throw new Error('Expected the stopped turn');
    act(() => result.current.retry(turn));
    act(() => vi.runAllTimers());
    expect(result.current.session.turns).toHaveLength(1);
    expect(result.current.session.turns[0]).toMatchObject({
      id: turn.id,
      answer: exampleAnswer(question),
      status: 'success',
    });
  });

  it('stops a request before its first chunk', () => {
    const { result } = renderHook(useDemoChat);
    act(() => {
      result.current.send(question);
      result.current.stop();
    });
    act(() => vi.runAllTimers());
    expect(result.current.session.turns[0]).toMatchObject({
      answer: '',
      status: 'abort',
    });
    expect(result.current.running).toBe(false);
  });

  it('cancels generation on creation and selection without mixing sessions', () => {
    const { result } = renderHook(useDemoChat);
    const firstId = result.current.session.id;
    act(() => result.current.send(question));
    act(() => result.current.newSession());
    const secondId = result.current.session.id;
    expect(secondId).not.toBe(firstId);
    expect(result.current.session.turns).toEqual([]);
    expect(vi.getTimerCount()).toBe(0);
    act(() => result.current.send('如何提交 IT 工单？'));
    act(() => vi.advanceTimersByTime(70));
    const partial = result.current.session.turns[0]?.answer;
    act(() => result.current.selectSession(firstId));
    act(() => vi.runAllTimers());
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

  it('atomically deletes multiple sessions and keeps a usable empty session', () => {
    const { result } = renderHook(useDemoChat);
    const firstId = result.current.session.id;
    act(() => result.current.send(question));
    act(() => result.current.newSession());
    const secondId = result.current.session.id;
    act(() => result.current.send(question));
    act(() => {
      result.current.deleteSession(firstId);
      result.current.deleteSession(secondId);
    });
    act(() => vi.runAllTimers());
    expect(result.current.sessions).toHaveLength(1);
    expect(result.current.session.turns).toEqual([]);
    expect(result.current.session.id).not.toBe(firstId);
    expect(result.current.session.id).not.toBe(secondId);
    expect(vi.getTimerCount()).toBe(0);
    act(() => expect(result.current.send(question)).toBe(true));
    act(() => vi.runAllTimers());
    expect(result.current.session.turns[0]?.status).toBe('success');
  });

  it('keeps a renamed title through follow-up questions and isolates feedback', () => {
    const { result } = renderHook(useDemoChat);
    act(() => result.current.send(question));
    act(() => vi.runAllTimers());
    const turn = result.current.session.turns[0];
    if (!turn) throw new Error('Expected the completed turn');
    act(() => {
      result.current.renameSession(result.current.session.id, '  网络支持  ');
      result.current.feedback(turn.id, 'like');
    });
    act(() => result.current.send('如何提交 IT 工单？'));
    act(() => vi.runAllTimers());
    expect(result.current.session.title).toBe('网络支持');
    expect(result.current.session.turns[0]?.feedback).toBe('like');
    expect(result.current.session.turns[1]?.feedback).toBeNull();
    act(() => result.current.feedback(turn.id, null));
    expect(result.current.session.turns[0]?.feedback).toBeNull();
    act(() => result.current.renameSession(result.current.session.id, '  '));
    expect(result.current.session.title).toBe('网络支持');
  });

  it('rejects retries from another session', () => {
    const { result } = renderHook(useDemoChat);
    act(() => result.current.send(question));
    act(() => vi.runAllTimers());
    const turn = result.current.session.turns[0];
    if (!turn) throw new Error('Expected a completed turn');
    act(() => result.current.newSession());
    act(() => result.current.retry(turn));
    expect(result.current.session.turns).toEqual([]);
    expect(vi.getTimerCount()).toBe(0);
  });

  it('releases generation timers on unmount under Strict Mode', () => {
    const { result, unmount } = renderHook(useDemoChat, {
      wrapper: StrictMode,
    });
    act(() => result.current.send(question));
    expect(vi.getTimerCount()).toBe(1);
    unmount();
    expect(vi.getTimerCount()).toBe(0);
  });
});
