import messages from './locales.zh-CN';

type MessageDescriptor = {
  id: string;
  defaultMessage?: string;
};

function translate(desc: MessageDescriptor): string {
  return desc.defaultMessage ?? messages[desc.id] ?? desc.id;
}

/** 对应原 Umi 的 getIntl() 静态调用 */
export function getIntl() {
  return {
    formatMessage: (desc: MessageDescriptor) => translate(desc),
  };
}

/** 对应原 Umi 的 useIntl() */
export function useIntl() {
  return {
    formatMessage: (desc: MessageDescriptor) => translate(desc),
  };
}

export function getLocale(): string {
  return 'zh-CN';
}

export function getAllLocales(): string[] {
  return ['zh-CN'];
}

export function setLocale(): void {
  // 单语后台：语言切换为 no-op
}
