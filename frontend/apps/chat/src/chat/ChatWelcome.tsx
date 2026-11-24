import {
  AppstoreOutlined,
  RobotOutlined,
  ToolOutlined,
} from '@ant-design/icons';
import { Prompts, Welcome } from '@ant-design/x';
import { promptGroups } from './demo-content';
import styles from './ChatPage.module.css';

export function ChatWelcome({
  onPrompt,
}: {
  onPrompt: (prompt: string) => void;
}) {
  return (
    <div className={styles.welcome}>
      <Welcome
        className={styles.welcomeBanner ?? ''}
        variant="borderless"
        icon={
          <span className={styles.welcomeIcon}>
            <RobotOutlined />
          </span>
        }
        title="你好，我是 IT 知识助手"
        description="试试询问账号、网络或办公设备相关的问题。"
      />
      <div className={styles.promptGrid}>
        {promptGroups.map(({ title, prompts }, index) => (
          <Prompts
            key={title}
            className={styles.promptCard}
            items={[
              {
                key: title,
                icon: index === 0 ? <ToolOutlined /> : <AppstoreOutlined />,
                label: title,
                children: prompts.map((prompt) => ({
                  key: prompt,
                  description: prompt,
                })),
              },
            ]}
            styles={{
              list: { width: '100%' },
              item: { flex: 1, border: 0, background: 'transparent' },
            }}
            onItemClick={({ data }) => {
              if (prompts.includes(data.key)) onPrompt(data.key);
            }}
          />
        ))}
      </div>
    </div>
  );
}
