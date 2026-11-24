import { useState } from 'react';
import type { CSSProperties } from 'react';
import { MenuOutlined } from '@ant-design/icons';
import { Button, Drawer, theme } from 'antd';
import { ChatComposer } from './ChatComposer';
import { ChatWelcome } from './ChatWelcome';
import { ConversationSidebar } from './ConversationSidebar';
import { MessageTimeline } from './MessageTimeline';
import { useDemoChat } from './use-demo-chat';
import styles from './ChatPage.module.css';

export function ChatPage() {
  const chat = useDemoChat();
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
        </header>
        {chat.session.turns.length > 0 ? (
          <MessageTimeline
            key={`timeline-${chat.session.id}`}
            turns={chat.session.turns}
            running={chat.running}
            onRetry={chat.retry}
            onFeedback={chat.feedback}
          />
        ) : (
          <ChatWelcome onPrompt={chat.send} />
        )}
        <ChatComposer
          key={`composer-${chat.session.id}`}
          running={chat.running}
          onSend={chat.send}
          onStop={chat.stop}
        />
      </main>
    </div>
  );
}
