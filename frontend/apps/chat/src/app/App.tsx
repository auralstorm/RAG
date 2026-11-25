import { useEffect, useState } from 'react';
import { ChatPage } from '../features/chat/pages/ChatPage';
import type { ChatReplySource } from '../features/chat/types';
import { AppProviders } from './AppProviders';
import { loadReplySource } from './load-reply-source';

export function App() {
  const [replySource, setReplySource] = useState<ChatReplySource | null>();
  const [initializationFailed, setInitializationFailed] = useState(false);
  useEffect(() => {
    let active = true;
    void loadReplySource().then(
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
  }, []);
  return (
    <AppProviders>
      <ChatPage
        replySource={replySource ?? null}
        isInitializing={replySource === undefined}
        initializationFailed={initializationFailed}
      />
    </AppProviders>
  );
}
