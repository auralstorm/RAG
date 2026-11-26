import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { App as AntdApp, ConfigProvider } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import { HelmetProvider } from 'react-helmet-async';
import { RouterProvider } from 'react-router';

import { ErrorBoundary, OfflineBanner } from '@/components';
import useGlobalStyles from '@/global.style';
import { router } from '@/routes';

const queryClient = new QueryClient();

export function Root() {
  useGlobalStyles();

  return (
    <ConfigProvider
      locale={zhCN}
      theme={{
        token: {
          fontFamily: 'AlibabaSans, sans-serif',
        },
      }}
    >
      <AntdApp>
        <HelmetProvider>
          <ErrorBoundary>
            <OfflineBanner />
            <QueryClientProvider client={queryClient}>
              <RouterProvider router={router} />
            </QueryClientProvider>
          </ErrorBoundary>
        </HelmetProvider>
      </AntdApp>
    </ConfigProvider>
  );
}
