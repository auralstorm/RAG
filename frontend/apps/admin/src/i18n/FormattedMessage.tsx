import type React from 'react';

import messages from './locales.zh-CN';

type FormattedMessageProps = {
  id: string;
  defaultMessage?: string;
  values?: Record<string, unknown>;
};

/** 对应原 Umi 的 <FormattedMessage /> */
export const FormattedMessage: React.FC<FormattedMessageProps> = ({
  id,
  defaultMessage,
}) => <>{defaultMessage ?? messages[id] ?? id}</>;
