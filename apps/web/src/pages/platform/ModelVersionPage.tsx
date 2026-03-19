import React from 'react';
import { ZCard, ZBadge } from '../../design-system/components';
import type { ZTableColumn } from '../../design-system/components';
import ZTable from '../../design-system/components/ZTable';
import styles from './ModelVersionPage.module.css';

// ── 类型 ─────────────────────────────────────────────────────────────────────

interface ModelItem {
  id: string;
  name: string;
  version: string;
  size: string;
  accuracy: string;
  env: string;
  updatedAt: string;
}

// ── Mock 数据 ────────────────────────────────────────────────────────────────

const MOCK_MODELS: ModelItem[] = [
  { id: 'M001', name: '需求预测模型', version: 'v3.2.1', size: '245MB', accuracy: '94.2%', env: '生产', updatedAt: '2026-03-15' },
  { id: 'M002', name: '损耗预测模型', version: 'v2.8.0', size: '180MB', accuracy: '91.5%', env: '生产', updatedAt: '2026-03-10' },
  { id: 'M003', name: '排班优化模型', version: 'v2.1.3', size: '120MB', accuracy: '89.8%', env: '生产', updatedAt: '2026-03-12' },
  { id: 'M004', name: '价格弹性模型', version: 'v1.5.0', size: '95MB', accuracy: '87.3%', env: '测试', updatedAt: '2026-03-16' },
  { id: 'M005', name: '会员流失模型', version: 'v2.0.2', size: '150MB', accuracy: '92.1%', env: '生产', updatedAt: '2026-03-08' },
  { id: 'M006', name: '菜品推荐模型', version: 'v1.8.1', size: '210MB', accuracy: '88.6%', env: '灰度', updatedAt: '2026-03-14' },
  { id: 'M007', name: '异常检测模型', version: 'v3.0.0', size: '78MB', accuracy: '95.3%', env: '生产', updatedAt: '2026-03-11' },
  { id: 'M008', name: '情感分析模型', version: 'v1.2.0', size: '320MB', accuracy: '86.9%', env: '测试', updatedAt: '2026-03-17' },
];

// ── 组件 ─────────────────────────────────────────────────────────────────────

const ModelVersionPage: React.FC = () => {
  const columns: ZTableColumn<ModelItem>[] = [
    { key: 'name', dataIndex: 'name', title: '模型名' },
    { key: 'version', dataIndex: 'version', title: '版本' },
    { key: 'size', dataIndex: 'size', title: '大小', align: 'right',
      render: (v: string) => <span className={styles.sizeCell}>{v}</span>,
    },
    { key: 'accuracy', dataIndex: 'accuracy', title: '精度', align: 'center',
      render: (v: string) => <span className={styles.accuracyCell}>{v}</span>,
    },
    { key: 'env', dataIndex: 'env', title: '部署环境',
      render: (v: string) => {
        const typeMap: Record<string, 'success' | 'warning' | 'info'> = {
          '生产': 'success', '灰度': 'warning', '测试': 'info',
        };
        return <ZBadge type={typeMap[v] || 'default'} text={v} />;
      },
    },
    { key: 'updatedAt', dataIndex: 'updatedAt', title: '更新时间' },
    { key: 'actions', title: '操作',
      render: () => (
        <div className={styles.actionGroup}>
          <button className={`${styles.actionBtn} ${styles.actionBtnPrimary}`}>部署</button>
          <button className={styles.actionBtn}>回滚</button>
          <button className={styles.actionBtn}>对比</button>
        </div>
      ),
    },
  ];

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <h2>模型版本</h2>
        <p>LLM 模型版本管理，灰度发布与回滚控制</p>
      </div>

      <div className={styles.section}>
        <div className={styles.sectionTitle}>模型注册表</div>
        <ZCard noPadding>
          <ZTable<ModelItem>
            columns={columns}
            dataSource={MOCK_MODELS}
            rowKey="id"
          />
        </ZCard>
      </div>
    </div>
  );
};

export default ModelVersionPage;
