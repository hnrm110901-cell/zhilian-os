import React, { useState } from 'react';
import { ZCard, ZBadge, ZTable, ZButton } from '../../design-system/components';
import type { ZTableColumn } from '../../design-system/components';
import styles from './BomImportPage.module.css';

/* ── Mock 数据 ── */

interface BomImportRecord {
  time: string;
  fileName: string;
  bomCount: number;
  linkedDishes: number;
  success: number;
  failed: number;
}

const importHistory: BomImportRecord[] = [
  { time: '2026-03-15 16:00', fileName: '春季BOM_v2.xlsx', bomCount: 38, linkedDishes: 45, success: 37, failed: 1 },
  { time: '2026-03-08 11:20', fileName: '饮品BOM更新.csv', bomCount: 12, linkedDishes: 12, success: 12, failed: 0 },
  { time: '2026-03-01 09:30', fileName: '套餐BOM.xlsx', bomCount: 8, linkedDishes: 8, success: 8, failed: 0 },
  { time: '2026-02-25 14:45', fileName: '全量BOM_v3.xlsx', bomCount: 120, linkedDishes: 156, success: 116, failed: 4 },
  { time: '2026-02-18 10:10', fileName: '原料替换BOM.csv', bomCount: 15, linkedDishes: 22, success: 15, failed: 0 },
];

const stepLabels = ['上传文件', '字段映射', '数据预览', '确认导入'];

/* ── 列定义 ── */

const historyColumns: ZTableColumn<BomImportRecord>[] = [
  { key: 'time', dataIndex: 'time', title: '时间', width: 150 },
  { key: 'fileName', dataIndex: 'fileName', title: '文件名' },
  { key: 'bomCount', dataIndex: 'bomCount', title: 'BOM数', width: 80, align: 'right' },
  { key: 'linkedDishes', dataIndex: 'linkedDishes', title: '关联菜品', width: 90, align: 'right' },
  {
    key: 'success', dataIndex: 'success', title: '成功', width: 70, align: 'right',
  },
  {
    key: 'failed', dataIndex: 'failed', title: '失败', width: 70, align: 'right',
    render: (v: number) => (
      <span>{v > 0 ? <ZBadge type="critical" text={String(v)} /> : v}</span>
    ),
  },
];

/* ── 页面组件 ── */

const BomImportPage: React.FC = () => {
  const [currentStep] = useState(0);

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <h1 className={styles.title}>BOM导入</h1>
        <p className={styles.subtitle}>批量导入物料清单数据，支持版本管理与差异对比</p>
      </div>

      {/* 步骤条 */}
      <div className={styles.steps}>
        {stepLabels.map((label, i) => (
          <React.Fragment key={label}>
            <div className={styles.step}>
              <div className={`${styles.stepCircle} ${i < currentStep ? styles.stepCircleDone : i === currentStep ? styles.stepCircleActive : ''}`}>
                {i < currentStep ? '✓' : i + 1}
              </div>
              <span className={`${styles.stepLabel} ${i === currentStep ? styles.stepLabelActive : ''}`}>
                {label}
              </span>
            </div>
            {i < stepLabels.length - 1 && (
              <div className={`${styles.stepLine} ${i < currentStep ? styles.stepLineDone : ''}`} />
            )}
          </React.Fragment>
        ))}
      </div>

      {/* 上传区域 */}
      <div className={styles.section}>
        <ZCard title="上传文件">
          <div className={styles.uploadZone}>
            <div className={styles.uploadIcon}>&#128194;</div>
            <p className={styles.uploadTitle}>点击或拖拽BOM文件到此区域</p>
            <p className={styles.uploadHint}>支持 .xlsx / .csv 格式，单次最大 10MB</p>
            <div className={styles.uploadFormats}>
              <ZBadge type="info" text="Excel (.xlsx)" />
              <ZBadge type="info" text="CSV (.csv)" />
            </div>
          </div>
          <div>
            <ZButton variant="ghost" size="sm">下载BOM模板</ZButton>
          </div>
        </ZCard>
      </div>

      {/* 导入历史 */}
      <div className={styles.section}>
        <ZCard title="导入历史">
          {/* GET /api/v1/ops/bom-import-history */}
          <ZTable<BomImportRecord> columns={historyColumns} data={importHistory} rowKey="time" />
        </ZCard>
      </div>
    </div>
  );
};

export default BomImportPage;
