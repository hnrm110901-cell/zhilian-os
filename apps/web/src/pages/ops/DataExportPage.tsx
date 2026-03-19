import React, { useState } from 'react';
import { ZCard, ZBadge } from '../../design-system/components';
import type { ZTableColumn } from '../../design-system/components';
import ZTable from '../../design-system/components/ZTable';
import styles from './DataExportPage.module.css';

// ── 类型 ─────────────────────────────────────────────────────────────────────

interface ExportTask {
  id: string;
  time: string;
  template: string;
  store: string;
  format: string;
  size: string;
  status: string;
}

// ── Mock 数据 ────────────────────────────────────────────────────────────────

const EXPORT_TEMPLATES = [
  { key: 'daily', label: '日报', icon: '📊' },
  { key: 'weekly', label: '周报', icon: '📈' },
  { key: 'orders', label: '订单明细', icon: '📋' },
  { key: 'inventory', label: '库存快照', icon: '📦' },
  { key: 'members', label: '会员列表', icon: '💳' },
];

const MOCK_TASKS: ExportTask[] = [
  { id: 'E001', time: '2026-03-17 08:00', template: '日报', store: '全部门店', format: 'Excel', size: '2.3MB', status: '已完成' },
  { id: 'E002', time: '2026-03-16 18:00', template: '订单明细', store: '五一店', format: 'CSV', size: '5.1MB', status: '已完成' },
  { id: 'E003', time: '2026-03-15 09:00', template: '库存快照', store: '全部门店', format: 'Excel', size: '1.8MB', status: '已完成' },
  { id: 'E004', time: '2026-03-14 10:00', template: '周报', store: '全部门店', format: 'PDF', size: '3.5MB', status: '已完成' },
  { id: 'E005', time: '2026-03-13 14:30', template: '会员列表', store: '万达店', format: 'CSV', size: '890KB', status: '已完成' },
];

// ── 组件 ─────────────────────────────────────────────────────────────────────

const DataExportPage: React.FC = () => {
  const [selectedTemplate, setSelectedTemplate] = useState('daily');

  const columns: ZTableColumn<ExportTask>[] = [
    { key: 'time', dataIndex: 'time', title: '时间' },
    { key: 'template', dataIndex: 'template', title: '模板' },
    { key: 'store', dataIndex: 'store', title: '门店' },
    { key: 'format', dataIndex: 'format', title: '格式',
      render: (v: string) => <ZBadge type="info" text={v} />,
    },
    { key: 'size', dataIndex: 'size', title: '大小', align: 'right' },
    { key: 'status', dataIndex: 'status', title: '状态',
      render: (v: string) => (
        <ZBadge type={v === '已完成' ? 'success' : 'warning'} text={v} />
      ),
    },
    { key: 'download', title: '下载',
      render: () => <button className={styles.downloadBtn}>下载</button>,
    },
  ];

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <h2>数据导出</h2>
        <p>商户数据导出与报表下载，支持定时任务</p>
      </div>

      {/* 导出模板选择 */}
      <div className={styles.section}>
        <div className={styles.sectionTitle}>选择导出模板</div>
        <div className={styles.cardGrid}>
          {EXPORT_TEMPLATES.map((t) => (
            <ZCard
              key={t.key}
              className={`${styles.templateCard} ${selectedTemplate === t.key ? styles.templateCardActive : ''}`}
              onClick={() => setSelectedTemplate(t.key)}
            >
              <div className={styles.templateIcon}>{t.icon}</div>
              <div className={styles.templateName}>{t.label}</div>
            </ZCard>
          ))}
        </div>
      </div>

      {/* 筛选条件 */}
      <div className={styles.section}>
        <div className={styles.sectionTitle}>筛选条件</div>
        <div className={styles.filterBar}>
          <span className={styles.filterLabel}>时间范围</span>
          <input className={styles.filterInput} type="date" defaultValue="2026-03-01" />
          <span style={{ color: 'var(--text-tertiary)' }}>至</span>
          <input className={styles.filterInput} type="date" defaultValue="2026-03-17" />
          <span className={styles.filterLabel}>门店</span>
          <select className={styles.filterSelect}>
            <option>全部门店</option>
            <option>五一店</option>
            <option>万达店</option>
            <option>河西店</option>
          </select>
          <span className={styles.filterLabel}>格式</span>
          <select className={styles.filterSelect}>
            <option>Excel</option>
            <option>CSV</option>
            <option>PDF</option>
          </select>
          <button className={styles.exportBtn}>开始导出</button>
        </div>
      </div>

      {/* 导出任务 */}
      <div className={styles.section}>
        <div className={styles.sectionTitle}>导出任务</div>
        <ZCard noPadding>
          <ZTable<ExportTask>
            columns={columns}
            dataSource={MOCK_TASKS}
            rowKey="id"
          />
        </ZCard>
      </div>
    </div>
  );
};

export default DataExportPage;
