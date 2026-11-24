import { XProvider } from '@ant-design/x';
import zhCNX from '@ant-design/x/locale/zh_CN';
import zhCN from 'antd/locale/zh_CN';
import { ChatPage } from './chat/ChatPage';

const locale = { ...zhCN, ...zhCNX };
const theme = { token: { colorTextPlaceholder: '#6b7280' } };

export function App() {
  return (
    <XProvider locale={locale} theme={theme}>
      <ChatPage />
    </XProvider>
  );
}
