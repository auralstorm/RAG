import dayjs from 'dayjs';
import relativeTime from 'dayjs/plugin/relativeTime';
import 'dayjs/locale/zh-cn';
import ReactDOM from 'react-dom/client';

import '@/global.less';
import '@root/tailwind.css';
import { Root } from '@/app/Root';
import { bootstrapInitialState } from '@/stores/initialState';

dayjs.extend(relativeTime);
dayjs.locale('zh-cn');

async function bootstrap() {
  await bootstrapInitialState();
  ReactDOM.createRoot(document.getElementById('root')!).render(<Root />);
}

void bootstrap();
