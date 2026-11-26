import { Skeleton } from 'antd';
import type React from 'react';

const Loading: React.FC = () => (
  <Skeleton style={{ padding: '24px 40px', height: '60vh' }} active />
);

export default Loading;
