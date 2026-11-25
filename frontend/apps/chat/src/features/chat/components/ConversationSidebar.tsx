import { useState } from 'react';
import {
  CommentOutlined,
  DeleteOutlined,
  EditOutlined,
  EllipsisOutlined,
  PlusOutlined,
  RobotOutlined,
} from '@ant-design/icons';
import { Conversations } from '@ant-design/x';
import { Button, Input, Modal } from 'antd';
import type { ChatSession } from '../types';
import styles from '../styles/Chat.module.css';

interface SidebarProps {
  sessions: readonly ChatSession[];
  activeId: string;
  canCreate: boolean;
  onSelect: (id: string) => void;
  onCreate: () => void;
  onDelete: (id: string) => void;
  onRename: (id: string, title: string) => void;
}

export function ConversationSidebar({
  sessions,
  activeId,
  canCreate,
  onSelect,
  onCreate,
  onDelete,
  onRename,
}: SidebarProps) {
  const [renaming, setRenaming] = useState<string | null>(null);
  const [title, setTitle] = useState('');

  function saveTitle() {
    if (renaming === null || !title.trim()) return;
    onRename(renaming, title);
    setRenaming(null);
  }

  return (
    <>
      <div className={styles.brand}>
        <span className={styles.brandIcon}>
          <RobotOutlined />
        </span>
        IT 知识助手
      </div>
      <Button
        className={styles.createButton ?? ''}
        icon={<PlusOutlined />}
        disabled={!canCreate}
        onClick={onCreate}
      >
        新建对话
      </Button>
      <Conversations
        className={styles.conversations}
        items={sessions.map(({ id, title }) => ({
          key: id,
          label: (
            <Button
              type="text"
              className={styles.sessionButton ?? ''}
              aria-current={id === activeId ? 'page' : undefined}
              title={title}
              onClick={(event) => {
                event.stopPropagation();
                onSelect(id);
              }}
            >
              {title}
            </Button>
          ),
          icon: <CommentOutlined />,
          group: '本次会话',
        }))}
        activeKey={activeId}
        onActiveChange={onSelect}
        groupable
        menu={({ key }) => ({
          trigger: (
            <Button
              type="text"
              aria-label={`对话操作：${sessions.find((item) => item.id === key)?.title ?? ''}`}
              icon={<EllipsisOutlined />}
            />
          ),
          items: [
            {
              key: 'rename',
              label: '重命名',
              icon: <EditOutlined />,
              onClick: () => {
                setTitle(sessions.find((item) => item.id === key)?.title ?? '');
                setRenaming(key);
              },
            },
            {
              key: 'delete',
              label: '删除',
              icon: <DeleteOutlined />,
              danger: true,
              onClick: () => onDelete(key),
            },
          ],
        })}
      />
      <div className={styles.sidebarFooter}>IT 内部服务台</div>
      <Modal
        title="重命名对话"
        open={renaming !== null}
        onOk={saveTitle}
        onCancel={() => setRenaming(null)}
        okButtonProps={{ disabled: !title.trim() }}
      >
        <Input
          aria-label="对话名称"
          value={title}
          maxLength={64}
          onChange={(event) => setTitle(event.target.value)}
          onPressEnter={saveTitle}
        />
      </Modal>
    </>
  );
}
