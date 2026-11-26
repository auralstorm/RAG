import { MenuOutlined } from '@ant-design/icons';
import { Alert, Button, Drawer, theme } from 'antd';
import { useState } from 'react';
import type { CSSProperties } from 'react';

import { SessionLogoutButton } from '@enterprise-rag/ui';

import type { ChatReplySource } from './chat.types';
import { ChatComposer } from './components/ChatComposer';
import { ChatWelcome } from './components/ChatWelcome';
import { ConversationSidebar } from './components/ConversationSidebar';
import { MessageTimeline } from './components/MessageTimeline';
import { useChat } from './hooks/useChat';
import styles from './styles/chat.module.css';

interface ChatPageProps {
  readonly replySource: ChatReplySource | null;
  readonly isInitializing?: boolean;
  readonly initializationFailed?: boolean;
}

export function ChatPage({
  replySource,
  isInitializing = false,
  initializationFailed = false,
}: ChatPageProps) {
  const chat = useChat(replySource);
  const lastStatus = chat.session.turns.at(-1)?.status;
  const [historyOpen, setHistoryOpen] = useState(false);
  const { token } = theme.useToken();
  const palette: CSSProperties & Record<`--chat-${string}`, string> = {
    '--chat-surface': token.colorBgContainer,
    '--chat-sidebar': token.colorBgLayout,
    '--chat-border': token.colorBorderSecondary,
    '--chat-muted': token.colorTextSecondary,
    '--chat-text': token.colorText,
    '--chat-accent': token.colorPrimary,
    '--chat-accent-surface': token.colorPrimaryBg,
  };

  const sidebar = (
    <ConversationSidebar
      sessions={chat.sessions}
      activeId={chat.session.id}
      canCreate={chat.session.turns.length > 0}
      onSelect={(id) => {
        chat.selectSession(id);
        setHistoryOpen(false);
      }}
      onCreate={() => {
        chat.newSession();
        setHistoryOpen(false);
      }}
      onDelete={chat.deleteSession}
      onRename={chat.renameSession}
    />
  );

  return (
    <div className={styles.layout} style={palette}>
      <aside className={styles.sidebar} aria-label="对话历史">
        {sidebar}
      </aside>
      <Drawer
        title="对话历史"
        placement="left"
        open={historyOpen}
        rootStyle={palette}
        size="min(340px, 100vw)"
        onClose={() => setHistoryOpen(false)}
        styles={{ body: { display: 'flex', flexDirection: 'column' } }}
      >
        {historyOpen && sidebar}
      </Drawer>
      <main className={styles.main}>
        <span className={styles.screenReaderStatus} role="status">
          {chat.running
            ? '正在生成回答'
            : lastStatus === 'abort'
              ? '已停止生成'
              : lastStatus === 'success'
                ? '回答已完成'
                : lastStatus === 'error'
                  ? '回答生成失败'
                  : ''}
        </span>
        <header className={styles.header}>
          <Button
            className={styles.mobileMenu ?? ''}
            type="text"
            aria-label="打开对话历史"
            icon={<MenuOutlined />}
            onClick={() => setHistoryOpen(true)}
          />
          <h1 title={chat.session.title}>{chat.session.title}</h1>
          <SessionLogoutButton />
        </header>
        {!chat.canSend && (
          <Alert
            type={initializationFailed ? 'error' : 'info'}
            showIcon
            title={
              initializationFailed
                ? '问答服务初始化失败，请刷新页面重试。'
                : isInitializing
                  ? '正在初始化问答服务'
                  : '知识问答接口尚未接入'
            }
          />
        )}
        {chat.session.turns.length > 0 ? (
          <MessageTimeline
            key={`timeline-${chat.session.id}`}
            turns={chat.session.turns}
            running={chat.running}
            onRetry={chat.retry}
            onFeedback={chat.feedback}
          />
        ) : (
          <ChatWelcome onPrompt={chat.send} disabled={!chat.canSend} />
        )}
        <ChatComposer
          key={`composer-${chat.session.id}`}
          running={chat.running}
          disabled={!chat.canSend}
          notice={replySource?.notice ?? '知识问答接口尚未接入'}
          onSend={chat.send}
          onStop={chat.stop}
        />
      </main>
    </div>
  );
}
