import React, { useState } from 'react';
import { ZCard, ZBadge } from '../../design-system/components';
import type { ZTableColumn } from '../../design-system/components';
import ZTable from '../../design-system/components/ZTable';
import styles from './KeyManagementPage.module.css';

// ── 类型 ─────────────────────────────────────────────────────────────────────

interface ApiKeyItem {
  id: string;
  name: string;
  type: string;
  maskedKey: string;
  createdAt: string;
  expiresAt: string;
  status: string;
}

// ── Mock 数据 ────────────────────────────────────────────────────────────────

const MOCK_KEYS: ApiKeyItem[] = [
  { id: 'K001', name: '尝在一起-生产Key', type: 'Production', maskedKey: 'zl-prod-***...a8f2', createdAt: '2026-01-10', expiresAt: '2027-01-10', status: '正常' },
  { id: 'K002', name: '徐记海鲜-生产Key', type: 'Production', maskedKey: 'zl-prod-***...b3c1', createdAt: '2026-01-15', expiresAt: '2027-01-15', status: '正常' },
  { id: 'K003', name: '最黔线-测试Key', type: 'Sandbox', maskedKey: 'zl-test-***...d4e5', createdAt: '2026-02-20', expiresAt: '2026-08-20', status: '正常' },
  { id: 'K004', name: '内部调试Key', type: 'Development', maskedKey: 'zl-dev-***...f6g7', createdAt: '2026-03-01', expiresAt: '2026-06-01', status: '正常' },
  { id: 'K005', name: '旧版兼容Key', type: 'Production', maskedKey: 'zl-prod-***...h8i9', createdAt: '2025-06-01', expiresAt: '2026-03-01', status: '已过期' },
  { id: 'K006', name: '尚宫厨-测试Key', type: 'Sandbox', maskedKey: 'zl-test-***...j0k1', createdAt: '2026-03-05', expiresAt: '2026-09-05', status: '正常' },
];

// ── 组件 ─────────────────────────────────────────────────────────────────────

const KeyManagementPage: React.FC = () => {
  const [search, setSearch] = useState('');

  const filtered = MOCK_KEYS.filter(
    (k) => k.name.includes(search) || k.type.includes(search),
  );

  const columns: ZTableColumn<ApiKeyItem>[] = [
    { key: 'name', dataIndex: 'name', title: '名称' },
    { key: 'type', dataIndex: 'type', title: '类型',
      render: (v: string) => {
        const typeMap: Record<string, 'success' | 'info' | 'warning'> = {
          Production: 'success', Sandbox: 'info', Development: 'warning',
        };
        return <ZBadge type={typeMap[v] || 'default'} text={v} />;
      },
    },
    { key: 'maskedKey', dataIndex: 'maskedKey', title: 'Key',
      render: (v: string) => <span className={styles.maskedKey}>{v}</span>,
    },
    { key: 'createdAt', dataIndex: 'createdAt', title: '创建时间' },
    { key: 'expiresAt', dataIndex: 'expiresAt', title: '过期时间' },
    { key: 'status', dataIndex: 'status', title: '状态',
      render: (v: string) => (
        <ZBadge type={v === '正常' ? 'success' : 'error'} text={v} />
      ),
    },
    { key: 'actions', title: '操作',
      render: () => (
        <div className={styles.actionGroup}>
          <button className={styles.actionBtn}>轮换</button>
          <button className={`${styles.actionBtn} ${styles.actionBtnDanger}`}>吊销</button>
        </div>
      ),
    },
  ];

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <div className={styles.headerLeft}>
          <h2>密钥管理</h2>
          <p>API Key 发放与轮换，保障接口访问安全</p>
        </div>
        <div className={styles.headerActions}>
          <input
            className={styles.searchInput}
            placeholder="搜索密钥名称..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <button className={styles.createBtn}>+ 创建 Key</button>
        </div>
      </div>

      <div className={styles.section}>
        <ZCard noPadding>
          <ZTable<ApiKeyItem>
            columns={columns}
            dataSource={filtered}
            rowKey="id"
          />
        </ZCard>
      </div>
    </div>
  );
};

export default KeyManagementPage;
