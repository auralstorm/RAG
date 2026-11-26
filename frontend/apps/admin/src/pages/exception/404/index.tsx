import { Button, Card, Result } from 'antd';
import type React from 'react';
import { Link } from 'react-router';

import { useIntl } from '@/i18n/intl';

const Exception404: React.FC = () => {
  const intl = useIntl();
  return (
    <Card variant="borderless">
      <Result
        status="404"
        title="404"
        subTitle={intl.formatMessage({
          id: 'pages.404.subTitle',
          defaultMessage: '抱歉，您访问的页面不存在。',
        })}
        extra={
          <Link to="/">
            <Button type="primary">
              {intl.formatMessage({
                id: 'pages.404.buttonText',
                defaultMessage: '返回首页',
              })}
            </Button>
          </Link>
        }
      />
    </Card>
  );
};

export default Exception404;
