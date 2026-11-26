import axios, { type AxiosRequestConfig } from 'axios';

import { errorHandler, errorThrower } from '@/requestErrorConfig';

export interface RequestOptions extends AxiosRequestConfig {
  skipErrorHandler?: boolean;
}

const baseURL = import.meta.env.DEV
  ? ''
  : 'https://pro-api.ant-design-demo.workers.dev';

const instance = axios.create({
  baseURL,
  timeout: 30000,
});

// 请求拦截器：预留 token 注入（与原项目一致，默认关闭）
instance.interceptors.request.use((config) => {
  // const token = localStorage.getItem('token');
  // if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

// 响应拦截器：业务错误抛出 BizError
instance.interceptors.response.use(
  (response) => {
    errorThrower(response.data);
    return response.data;
  },
  (error) => Promise.reject(error),
);

/**
 * 对应原 Umi 的 request：返回响应体 JSON，错误走统一 errorHandler
 */
export async function request<T = unknown>(
  url: string,
  options: RequestOptions = {},
): Promise<T> {
  const { skipErrorHandler, ...config } = options;
  try {
    return (await instance.request({ url, ...config })) as T;
  } catch (error) {
    errorHandler(error, { skipErrorHandler });
    throw error;
  }
}

export default request;
