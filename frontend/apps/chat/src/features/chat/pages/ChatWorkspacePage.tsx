import { useEffect, useState } from 'react';
import { ChatPage } from './ChatPage';
import type { ChatReplySource } from '../types';
import { loadReplySource } from '../../../app/load-reply-source';

export function ChatWorkspacePage({
  isPreview = false,
}: {
  readonly isPreview?: boolean;
}) {
  const [replySource, setReplySource] = useState<ChatReplySource | null>();
  const [initializationFailed, setInitializationFailed] = useState(false);
  useEffect(() => {
    let active = true;
    void loadReplySource(isPreview).then(
      (source) => {
        if (active) setReplySource(source);
      },
      () => {
        if (active) {
          setReplySource(null);
          setInitializationFailed(true);
        }
      },
    );
    return () => {
      active = false;
    };
  }, [isPreview]);
  return (
    <ChatPage
      replySource={replySource ?? null}
      isInitializing={replySource === undefined}
      initializationFailed={initializationFailed}
    />
  );
}
