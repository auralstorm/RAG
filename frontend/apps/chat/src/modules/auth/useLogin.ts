import { useEffect, useRef, useState } from 'react';
import type { LoginAction } from './auth.types';

export function useLogin(onLogin?: LoginAction) {
  const request = useRef<AbortController | null>(null);
  const [isSubmitting, setSubmitting] = useState(false);
  const [hasError, setError] = useState(false);

  useEffect(
    () => () => {
      request.current?.abort();
      request.current = null;
    },
    [],
  );

  async function handleLogin() {
    if (!onLogin || request.current) return;
    const controller = new AbortController();
    request.current = controller;
    setSubmitting(true);
    setError(false);
    try {
      await onLogin(controller.signal);
    } catch {
      if (!controller.signal.aborted) setError(true);
    } finally {
      if (request.current === controller) {
        request.current = null;
        setSubmitting(false);
      }
    }
  }

  return { handleLogin, isSubmitting, hasError };
}
