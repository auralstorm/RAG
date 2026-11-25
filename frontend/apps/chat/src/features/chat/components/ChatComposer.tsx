import { useState } from 'react';
import type { ComponentProps } from 'react';
import { PaperClipOutlined } from '@ant-design/icons';
import { Attachments, Prompts, Sender } from '@ant-design/x';
import { Button } from 'antd';
import styles from '../styles/Chat.module.css';

const shortcuts = ['如何申请 VPN 访问？', '如何提交 IT 工单？'];
type LocalFiles = NonNullable<ComponentProps<typeof Attachments>['items']>;

interface ComposerProps {
  readonly disabled: boolean;
  readonly notice: string;
  running: boolean;
  onSend: (question: string) => boolean;
  onStop: () => void;
}

export function ChatComposer({
  running,
  disabled,
  notice,
  onSend,
  onStop,
}: ComposerProps) {
  const [draft, setDraft] = useState('');
  const [attachmentsOpen, setAttachmentsOpen] = useState(false);
  const [files, setFiles] = useState<LocalFiles>([]);

  function submit(question: string) {
    if (onSend(question)) setDraft('');
  }

  return (
    <div className={styles.composer}>
      {!attachmentsOpen && (
        <Prompts
          wrap
          items={shortcuts.map((question) => ({
            key: question,
            label: question,
            disabled: running || disabled,
          }))}
          onItemClick={({ data }) => submit(data.key)}
        />
      )}
      <Sender
        aria-label="输入你的 IT 问题"
        value={draft}
        onChange={setDraft}
        onSubmit={submit}
        onCancel={onStop}
        loading={running}
        disabled={disabled}
        suffix={(_, { components: { SendButton, LoadingButton } }) =>
          running ? (
            <LoadingButton aria-label="停止生成" />
          ) : (
            <SendButton
              aria-label="发送问题"
              disabled={disabled || !draft.trim()}
            />
          )
        }
        placeholder="输入你的 IT 问题"
        prefix={
          <Button
            type="text"
            aria-label="附件预览"
            aria-expanded={attachmentsOpen}
            disabled={disabled}
            icon={<PaperClipOutlined />}
            onClick={() => setAttachmentsOpen((open) => !open)}
          />
        }
        header={
          <Sender.Header
            title="本地附件预览"
            open={attachmentsOpen}
            closable={false}
            onOpenChange={setAttachmentsOpen}
          >
            <Attachments
              items={files}
              beforeUpload={() => false}
              onChange={({ fileList }) => setFiles(fileList)}
              placeholder={{
                title: '选择或拖入文件',
                description: '文件仅在此处预览。',
              }}
            />
          </Sender.Header>
        }
      />
      <div className={styles.composerNote}>{notice}</div>
    </div>
  );
}
