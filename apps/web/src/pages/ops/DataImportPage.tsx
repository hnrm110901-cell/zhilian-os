import React, { useState } from 'react';
import { ZCard, ZBadge } from '../../design-system/components';
import type { ZTableColumn } from '../../design-system/components';
import ZTable from '../../design-system/components/ZTable';
import styles from './DataImportPage.module.css';

// ── 类型 ─────────────────────────────────────────────────────────────────────

interface ImportHistory {
  id: string;
  time: string;
  type: string;
  fileName: string;
  recordCount: number;
  successCount: number;
  failCount: number;
  status: string;
}

// ── Mock 数据 ────────────────────────────────────────────────────────────────

const DATA_TYPES = [
  { key: 'order', label: '订单', icon: '📋' },
  { key: 'inventory', label: '库存', icon: '📦' },
  { key: 'dish', label: '菜品', icon: '🍜' },
  { key: 'employee', label: '员工', icon: '👤' },
  { key: 'member', label: '会员', icon: '💳' },
];

const MOCK_HISTORY: ImportHistory[] = [
  { id: 'I001', time: '2026-03-17 08:30', type: '订单', fileName: 'orders_202603.xlsx', recordCount: 1250, successCount: 1248, failCount: 2, status: '已完成' },
  { id: 'I002', time: '2026-03-16 14:20', type: '库存', fileName: 'inventory_snapshot.csv', recordCount: 380, successCount: 380, failCount: 0, status: '已完成' },
  { id: 'I003', time: '2026-03-15 09:00', type: '菜品', fileName: 'menu_update.xlsx', recordCount: 85, successCount: 83, failCount: 2, status: '已完成' },
  { id: 'I004', time: '2026-03-14 16:45', type: '员工', fileName: 'staff_info.xlsx', recordCount: 42, successCount: 42, failCount: 0, status: '已完成' },
  { id: 'I005', time: '2026-03-13 11:30', type: '会员', fileName: 'members_export.csv', recordCount: 5200, successCount: 5180, failCount: 20, status: '已完成' },
  { id: 'I006', time: '2026-03-12 10:00', type: '订单', fileName: 'orders_history.xlsx', recordCount: 8500, successCount: 0, failCount: 0, status: '处理中' },
];

// ── 组件 ─────────────────────────────────────────────────────────────────────

const DataImportPage: React.FC = () => {
  const [selectedType, setSelectedType] = useState('order');

  const columns: ZTableColumn<ImportHistory>[] = [
    { key: 'time', dataIndex: 'time', title: '时间' },
    { key: 'type', dataIndex: 'type', title: '类型',
      render: (v: string) => <ZBadge type="info" text={v} />,
    },
    { key: 'fileName', dataIndex: 'fileName', title: '文件名' },
    { key: 'recordCount', dataIndex: 'recordCount', title: '记录数', align: 'right',
      render: (v: number) => v.toLocaleString(),
    },
    { key: 'successCount', dataIndex: 'successCount', title: '成功', align: 'right',
      render: (v: number) => v.toLocaleString(),
    },
    { key: 'failCount', dataIndex: 'failCount', title: '失败', align: 'right',
      render: (v: number) => v > 0 ? <span style={{ color: '#ef4444' }}>{v}</span> : <span>0</span>,
    },
    { key: 'status', dataIndex: 'status', title: '状态',
      render: (v: string) => (
        <ZBadge type={v === '已完成' ? 'success' : 'warning'} text={v} />
      ),
    },
  ];

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <h2>数据导入</h2>
        <p>通用数据批量导入，支持多种格式与映射配置</p>
      </div>

      {/* 数据类型选择 */}
      <div className={styles.section}>
        <div className={styles.sectionTitle}>选择数据类型</div>
        <div className={styles.cardGrid}>
          {DATA_TYPES.map((dt) => (
            <ZCard
              key={dt.key}
              className={`${styles.typeCard} ${selectedType === dt.key ? styles.typeCardActive : ''}`}
              onClick={() => setSelectedType(dt.key)}
            >
              <div className={styles.typeIcon}>{dt.icon}</div>
              <div className={styles.typeName}>{dt.label}</div>
            </ZCard>
          ))}
        </div>
      </div>

      {/* 上传区域 */}
      <div className={styles.section}>
        <div className={styles.sectionTitle}>上传文件</div>
        <div className={styles.uploadZone}>
          <div className={styles.uploadIcon}>&#8682;</div>
          <div className={styles.uploadText}>点击或拖拽文件到此区域上传</div>
          <div className={styles.uploadHint}>支持 .xlsx, .csv, .json 格式，单文件不超过 50MB</div>
        </div>
      </div>

      {/* 导入历史 */}
      <div className={styles.section}>
        <div className={styles.sectionTitle}>导入历史</div>
        <ZCard noPadding>
          <ZTable<ImportHistory>
            columns={columns}
            dataSource={MOCK_HISTORY}
            rowKey="id"
          />
        </ZCard>
      </div>
    </div>
  );
};

export default DataImportPage;
