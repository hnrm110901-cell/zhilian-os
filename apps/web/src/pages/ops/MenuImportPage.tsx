import React, { useState } from 'react';
import { ZCard, ZBadge, ZTable, ZButton } from '../../design-system/components';
import type { ZTableColumn } from '../../design-system/components';
import styles from './MenuImportPage.module.css';

/* ── Mock 数据 ── */

interface ImportRecord {
  time: string;
  fileName: string;
  dishCount: number;
  success: number;
  failed: number;
  operator: string;
}

const importHistory: ImportRecord[] = [
  { time: '2026-03-16 15:30', fileName: '春季新菜单.xlsx', dishCount: 45, success: 44, failed: 1, operator: '李店长' },
  { time: '2026-03-10 10:20', fileName: '饮品更新.csv', dishCount: 12, success: 12, failed: 0, operator: '王经理' },
  { time: '2026-03-05 09:15', fileName: '套餐组合.xlsx', dishCount: 8, success: 8, failed: 0, operator: '张主管' },
  { time: '2026-02-28 14:00', fileName: '全量菜单_v3.xlsx', dishCount: 156, success: 152, failed: 4, operator: '李店长' },
  { time: '2026-02-20 11:30', fileName: '下架菜品.csv', dishCount: 6, success: 6, failed: 0, operator: '王经理' },
];

const stepLabels = ['上传文件', '字段映射', '数据预览', '确认导入'];

/* ── 列定义 ── */

const historyColumns: ZTableColumn<ImportRecord>[] = [
  { key: 'time', dataIndex: 'time', title: '时间', width: 150 },
  { key: 'fileName', dataIndex: 'fileName', title: '文件名' },
  { key: 'dishCount', dataIndex: 'dishCount', title: '菜品数', width: 80, align: 'right' },
  {
    key: 'success', dataIndex: 'success', title: '成功', width: 70, align: 'right',
    render: (v: number) => <span>{v}</span>,
  },
  {
    key: 'failed', dataIndex: 'failed', title: '失败', width: 70, align: 'right',
    render: (v: number) => (
      <span>{v > 0 ? <ZBadge type="critical" text={String(v)} /> : v}</span>
    ),
  },
  { key: 'operator', dataIndex: 'operator', title: '操作人', width: 100 },
];

/* ── 页面组件 ── */

const MenuImportPage: React.FC = () => {
  const [currentStep] = useState(0);

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <h1 className={styles.title}>菜单导入</h1>
        <p className={styles.subtitle}>批量导入菜品数据，支持Excel和CSV格式</p>
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
            <p className={styles.uploadTitle}>点击或拖拽文件到此区域</p>
            <p className={styles.uploadHint}>支持 .xlsx / .csv 格式，单次最大 10MB</p>
            <div className={styles.uploadFormats}>
              <ZBadge type="info" text="Excel (.xlsx)" />
              <ZBadge type="info" text="CSV (.csv)" />
            </div>
          </div>
          <div>
            <ZButton variant="ghost" size="sm">下载导入模板</ZButton>
          </div>
        </ZCard>
      </div>

      {/* 导入历史 */}
      <div className={styles.section}>
        <ZCard title="导入历史">
          {/* GET /api/v1/ops/menu-import-history */}
          <ZTable<ImportRecord> columns={historyColumns} data={importHistory} rowKey="time" />
        </ZCard>
      </div>
    </div>
  );
};

export default MenuImportPage;
