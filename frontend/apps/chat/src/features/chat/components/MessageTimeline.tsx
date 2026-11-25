import {
  DislikeOutlined,
  LikeOutlined,
  RobotOutlined,
  SyncOutlined,
} from '@ant-design/icons';
import { Actions, Bubble, ThoughtChain } from '@ant-design/x';
import XMarkdown from '@ant-design/x-markdown';
import '@ant-design/x-markdown/themes/light.css';
import { Alert, Avatar, Button } from 'antd';
import type { ChatTurn } from '../types';
import styles from '../styles/Chat.module.css';

interface TimelineProps {
  turns: readonly ChatTurn[];
  running: boolean;
  onRetry: (turn: ChatTurn) => void;
  onFeedback: (id: string, feedback: ChatTurn['feedback']) => void;
}

const markdownPolicy = { FORBID_TAGS: ['img'] };

export function MessageTimeline({
  turns,
  running,
  onRetry,
  onFeedback,
}: TimelineProps) {
  return (
    <Bubble.List
      className={styles.timeline}
      autoScroll
      role={{
        user: { placement: 'end' },
        assistant: { variant: 'borderless' },
      }}
      items={turns.flatMap((turn) => {
        const busy = turn.status === 'loading' || turn.status === 'updating';
        return [
          { key: `${turn.id}-question`, role: 'user', content: turn.question },
          {
            key: turn.id,
            role: 'assistant',
            loading: turn.status === 'loading',
            streaming: busy,
            avatar: <Avatar icon={<RobotOutlined />} />,
            header: busy ? (
              <ThoughtChain.Item title="正在生成" status="loading" />
            ) : (
              'IT 知识助手'
            ),
            content: (
              <>
                <XMarkdown
                  className="x-markdown-light"
                  escapeRawHtml
                  openLinksInNewTab
                  dompurifyConfig={markdownPolicy}
                  streaming={{ hasNextChunk: busy }}
                >
                  {turn.answer}
                </XMarkdown>
                {turn.status === 'abort' && (
                  <span className={styles.muted}>已停止生成</span>
                )}
                {turn.status === 'error' && (
                  <Alert type="error" title="回答生成失败，请重试。" showIcon />
                )}
              </>
            ),
            footer: !busy && (
              <Actions
                items={[
                  ...(!running
                    ? [
                        {
                          key: 'retry',
                          actionRender: (
                            <Button
                              type="text"
                              aria-label="重新生成"
                              title="重新生成"
                              icon={<SyncOutlined />}
                              onClick={() => onRetry(turn)}
                            />
                          ),
                        },
                      ]
                    : []),
                  ...(turn.answer
                    ? [
                        {
                          key: 'copy',
                          actionRender: <Actions.Copy text={turn.answer} />,
                        },
                        {
                          key: 'feedback',
                          actionRender: (
                            <div
                              className={styles.feedback}
                              role="group"
                              aria-label="回答反馈"
                            >
                              <Button
                                type="text"
                                aria-label="有帮助"
                                aria-pressed={turn.feedback === 'like'}
                                icon={<LikeOutlined />}
                                onClick={() =>
                                  onFeedback(
                                    turn.id,
                                    turn.feedback === 'like' ? null : 'like',
                                  )
                                }
                              />
                              <Button
                                type="text"
                                aria-label="没有帮助"
                                aria-pressed={turn.feedback === 'dislike'}
                                icon={<DislikeOutlined />}
                                onClick={() =>
                                  onFeedback(
                                    turn.id,
                                    turn.feedback === 'dislike'
                                      ? null
                                      : 'dislike',
                                  )
                                }
                              />
                            </div>
                          ),
                        },
                      ]
                    : []),
                ]}
              />
            ),
          },
        ];
      })}
    />
  );
}
