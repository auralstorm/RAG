import { ReadOutlined } from '@ant-design/icons';
import { Link } from 'react-router';
import styles from './admin.module.css';

export function EnterpriseBrand() {
  return (
    <Link
      to="/admin"
      className={styles.brand}
      aria-label="EnterpriseRag 管理首页"
    >
      <ReadOutlined aria-hidden />
      <span>EnterpriseRag</span>
    </Link>
  );
}
