import { message, notification } from 'antd';

import { getIntl } from '@/i18n/intl';

// 错误处理方案： 错误类型（const 联合，满足 erasableSyntaxOnly）
const ErrorShowType = {
  SILENT: 0,
  WARN_MESSAGE: 1,
  ERROR_MESSAGE: 2,
  NOTIFICATION: 3,
  REDIRECT: 9,
} as const;

type ErrorShowType = (typeof ErrorShowType)[keyof typeof ErrorShowType];

// 与后端约定的响应数据格式
interface ResponseStructure {
  success: boolean;
  data: unknown;
  errorCode?: number;
  errorMessage?: string;
  showType?: ErrorShowType;
}

interface BizErrorInfo {
  errorCode?: number;
  errorMessage?: string;
  showType?: ErrorShowType;
  data: unknown;
}

type RequestError = Error & {
  info?: BizErrorInfo;
  response?: { status: number };
  request?: unknown;
};

/**
 * 业务错误抛出：响应体 success 为 false 时抛出 BizError
 */
export function errorThrower(res: unknown) {
  const { success, data, errorCode, errorMessage, showType } =
    res as ResponseStructure;
  // 仅在响应体显式携带 success 字段且为 false 时抛出业务错误；
  // 无 success 约定的响应（如登录接口）原样放行
  if (res && typeof res === 'object' && 'success' in res && !success) {
    const error = new Error(errorMessage) as RequestError;
    error.name = 'BizError';
    error.info = { errorCode, errorMessage, showType, data };
    throw error;
  }
}

/**
 * 统一错误接收及处理（移植自原 Umi Max request 插件的 errorConfig）
 */
export function errorHandler(
  error: unknown,
  opts?: { skipErrorHandler?: boolean },
) {
  const err = error as RequestError;
  if (opts?.skipErrorHandler) throw error;

  if (err.name === 'BizError') {
    const errorInfo: BizErrorInfo | undefined = err.info;
    if (errorInfo) {
      const { errorMessage, errorCode } = errorInfo;
      switch (errorInfo.showType) {
        case ErrorShowType.SILENT:
          break;
        case ErrorShowType.WARN_MESSAGE:
          message.warning(errorMessage);
          break;
        case ErrorShowType.ERROR_MESSAGE:
          message.error(errorMessage);
          break;
        case ErrorShowType.NOTIFICATION:
          notification.open({
            title: String(errorCode),
            description: errorMessage,
          });
          break;
        case ErrorShowType.REDIRECT:
          window.location.href = '/user/login';
          break;
        default:
          message.error(errorMessage);
      }
    }
  } else if (err.response) {
    message.error(`Response status:${err.response.status}`);
  } else if (typeof navigator !== 'undefined' && !navigator.onLine) {
    message.error(
      getIntl().formatMessage({
        id: 'app.request.offline',
        defaultMessage:
          'Network unavailable. Please check your connection and try again.',
      }),
    );
  } else if (err.request) {
    message.error('None response! Please retry.');
  } else {
    message.error('Request error, please retry.');
  }
}
