import React, { useState } from 'react';
import { ZCard, ZBadge, ZTable, ZButton, ZKpi } from '../../design-system/components';
import type { ZTableColumn } from '../../design-system/components';
import styles from './MenuImportPage.module.css';

/* ── Mock 数据 ── TODO: GET /api/v1/ops/menu-import-history */

interface ImportRecord {
  time: string;
  fileName: string;
  dishCount: number;
  success: number;
  failed: number;
  operator: string;
  status: string;
}

interface FieldMapping {
  sourceCol: string;
  targetField: string;
  sample: string;
  required: boolean;
  matched: boolean;
}

interface ConflictItem {
  dishCode: string;
  dishName: string;
  conflictType: string;
  currentValue: string;
  importValue: string;
}

const importHistory: ImportRecord[] = [
  { time: '2026-03-16 15:30', fileName: '春季新菜单.xlsx', dishCount: 45, success: 44, failed: 1, operator: '李店长', status: '完成' },
  { time: '2026-03-10 10:20', fileName: '饮品更新.csv', dishCount: 12, success: 12, failed: 0, operator: '王经理', status: '完成' },
  { time: '2026-03-05 09:15', fileName: '套餐组合.xlsx', dishCount: 8, success: 8, failed: 0, operator: '张主管', status: '完成' },
  { time: '2026-02-28 14:00', fileName: '全量菜单_v3.xlsx', dishCount: 156, success: 152, failed: 4, operator: '李店长', status: '完成' },
  { time: '2026-02-20 11:30', fileName: '下架菜品.csv', dishCount: 6, success: 6, failed: 0, operator: '王经理', status: '完成' },
];

const fieldMappings: FieldMapping[] = [
  { sourceCol: '菜品编码', targetField: 'dish_code', sample: 'D001', required: true, matched: true },
  { sourceCol: '菜品名称', targetField: 'dish_name', sample: '招牌剁椒鱼头', required: true, matched: true },
  { sourceCol: '分类', targetField: 'category', sample: '主菜', required: true, matched: true },
  { sourceCol: '售价', targetField: 'price', sample: '68.00', required: true, matched: true },
  { sourceCol: '成本价', targetField: 'cost_price', sample: '22.50', required: false, matched: true },
  { sourceCol: '单位', targetField: 'unit', sample: '份', required: true, matched: true },
  { sourceCol: '备注', targetField: 'remark', sample: '含辣椒过敏提示', required: false, matched: false },
];

const conflicts: ConflictItem[] = [
  { dishCode: 'D023', dishName: '夫妻肺片', conflictType: '价格变更', currentValue: '¥38', importValue: '¥42', },
  { dishCode: 'D047', dishName: '剁椒鱼头(中份)', conflictType: '分类变更', currentValue: '湘菜', importValue: '主菜', },
];

const stepLabels = ['上传文件', '字段映射', '数据预览', '确认导入'];

/* ── 列定义 ── */

const historyColumns: ZTableColumn<ImportRecord>[] = [
  { key: 'time', dataIndex: 'time', title: '时间', width: 150 },
  { key: 'fileName', dataIndex: 'fileName', title: '文件名' },
  { key: 'dishCount', dataIndex: 'dishCount', title: '菜品数', width: 80, align: 'right' },
  {
    key: 'success', dataIndex: 'success', title: '成功', width: 70, align: 'right',
    render: (v: number) => <span className={styles.successNum}>{v}</span>,
  },
  {
    key: 'failed', dataIndex: 'failed', title: '失败', width: 70, align: 'right',
    render: (v: number) => (
      v > 0 ? <ZBadge type="critical" text={String(v)} /> : <span className={styles.zeroNum}>{v}</span>
    ),
  },
  { key: 'operator', dataIndex: 'operator', title: '操作人', width: 100 },
  {
    key: 'status', dataIndex: 'status', title: '状态', width: 80,
    render: (v: string) => <ZBadge type="success" text={v} />,
  },
];

const mappingColumns: ZTableColumn<FieldMapping>[] = [
  { key: 'sourceCol', dataIndex: 'sourceCol', title: '源列名' },
  { key: 'targetField', dataIndex: 'targetField', title: '目标字段' },
  { key: 'sample', dataIndex: 'sample', title: '示例值' },
  {
    key: 'required', dataIndex: 'required', title: '必填', width: 70, align: 'center',
    render: (v: boolean) => v ? <ZBadge type="critical" text="必填" /> : <span className={styles.optional}>选填</span>,
  },
  {
    key: 'matched', dataIndex: 'matched', title: '映射状态', width: 100,
    render: (v: boolean) => <ZBadge type={v ? 'success' : 'warning'} text={v ? '已匹配' : '未映射'} />,
  },
];

const conflictColumns: ZTableColumn<ConflictItem>[] = [
  { key: 'dishCode', dataIndex: 'dishCode', title: '菜品编码', width: 100 },
  { key: 'dishName', dataIndex: 'dishName', title: '菜品名称' },
  {
    key: 'conflictType', dataIndex: 'conflictType', title: '冲突类型', width: 100,
    render: (v: string) => <ZBadge type="warning" text={v} />,
  },
  { key: 'currentValue', dataIndex: 'currentValue', title: '现有值' },
  { key: 'importValue', dataIndex: 'importValue', title: '导入值', render: (v: string) => <span className={styles.importVal}>{v}</span> },
];

/* ── 页面组件 ── */

const MenuImportPage: React.FC = () => {
  const [currentStep] = useState(0);
  const [dragOver, setDragOver] = useState(false);

  const totalDishes = importHistory.reduce((s, r) => s + r.dishCount, 0);
  const totalFailed = importHistory.reduce((s, r) => s + r.failed, 0);
  const successRate = Math.round(((totalDishes - totalFailed) / totalDishes) * 100);

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <div className={styles.headerLeft}>
          <h1 className={styles.title}>菜单导入</h1>
          <p className={styles.subtitle}>批量导入菜品数据，支持Excel和CSV格式，智能字段映射与冲突检测</p>
        </div>
        <ZButton variant="ghost" size="sm">下载导入模板</ZButton>
      </div>

      {/* KPI 摘要 */}
      <div className={styles.kpiRow}>
        <ZCard><ZKpi label="历史导入总菜品" value={totalDishes} changeLabel="累计" /></ZCard>
        <ZCard><ZKpi label="本月导入次数" value={3} changeLabel="次" /></ZCard>
        <ZCard><ZKpi label="成功率" value={successRate} unit="%" change={0.8} changeLabel="较上月" /></ZCard>
        <ZCard><ZKpi label="失败记录" value={totalFailed} color="var(--red)" changeLabel="条" /></ZCard>
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
          <div
            className={`${styles.uploadZone} ${dragOver ? styles.uploadZoneDragOver : ''}`}
            onDragOver={e => { e.preventDefault(); setDragOver(true); }}
            onDragLeave={() => setDragOver(false)}
            onDrop={e => { e.preventDefault(); setDragOver(false); }}
          >
            <div className={styles.uploadIcon}>📂</div>
            <p className={styles.uploadTitle}>点击或拖拽文件到此区域</p>
            <p className={styles.uploadHint}>支持 .xlsx / .csv 格式，单次最大 10MB</p>
            <div className={styles.uploadFormats}>
              <ZBadge type="info" text="Excel (.xlsx)" />
              <ZBadge type="info" text="CSV (.csv)" />
            </div>
          </div>
        </ZCard>
      </div>

      {/* 字段映射预览 */}
      <div className={styles.section}>
        <ZCard title="字段映射预览">
          <div className={styles.mappingHint}>
            <ZBadge type="warning" text="1个字段未映射" />
            <span className={styles.mappingHintText}>「备注」列未能自动匹配，请手动选择目标字段或忽略</span>
          </div>
          {/* TODO: GET /api/v1/ops/menu-import/field-mapping */}
          <ZTable<FieldMapping> columns={mappingColumns} data={fieldMappings} rowKey="sourceCol" />
        </ZCard>
      </div>

      {/* 冲突检测 */}
      <div className={styles.section}>
        <ZCard title="冲突检测">
          <div className={styles.conflictHeader}>
            <ZBadge type="warning" text={`发现 ${conflicts.length} 处冲突`} />
            <span className={styles.conflictHint}>请选择保留现有值或使用导入值</span>
          </div>
          {/* TODO: GET /api/v1/ops/menu-import/conflicts */}
          <ZTable<ConflictItem> columns={conflictColumns} data={conflicts} rowKey="dishCode" />
          <div className={styles.conflictActions}>
            <ZButton variant="ghost" size="sm">全部保留现有</ZButton>
            <ZButton variant="ghost" size="sm">全部使用导入值</ZButton>
          </div>
        </ZCard>
      </div>

      {/* 导入历史 */}
      <div className={styles.section}>
        <ZCard title="导入历史">
          {/* TODO: GET /api/v1/ops/menu-import-history */}
          <ZTable<ImportRecord> columns={historyColumns} data={importHistory} rowKey="time" />
        </ZCard>
      </div>
    </div>
  );
};

export default MenuImportPage;
