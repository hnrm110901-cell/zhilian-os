import React, { useState } from 'react';
import { ZCard, ZBadge, ZTable, ZButton, ZKpi } from '../../design-system/components';
import type { ZTableColumn } from '../../design-system/components';
import styles from './BomImportPage.module.css';

/* ── Mock 数据 ── TODO: GET /api/v1/ops/bom-import-history */

interface BomImportRecord {
  time: string;
  fileName: string;
  bomCount: number;
  linkedDishes: number;
  success: number;
  failed: number;
  operator: string;
}

interface BomFieldMapping {
  sourceCol: string;
  targetField: string;
  sample: string;
  required: boolean;
  matched: boolean;
}

interface BomPreviewRow {
  dishCode: string;
  dishName: string;
  ingredient: string;
  quantity: number;
  unit: string;
  costPerUnit: string;
}

const importHistory: BomImportRecord[] = [
  { time: '2026-03-15 16:00', fileName: '春季BOM_v2.xlsx', bomCount: 38, linkedDishes: 45, success: 37, failed: 1, operator: '张主管' },
  { time: '2026-03-08 11:20', fileName: '饮品BOM更新.csv', bomCount: 12, linkedDishes: 12, success: 12, failed: 0, operator: '王经理' },
  { time: '2026-03-01 09:30', fileName: '套餐BOM.xlsx', bomCount: 8, linkedDishes: 8, success: 8, failed: 0, operator: '李店长' },
  { time: '2026-02-25 14:45', fileName: '全量BOM_v3.xlsx', bomCount: 120, linkedDishes: 156, success: 116, failed: 4, operator: '张主管' },
  { time: '2026-02-18 10:10', fileName: '原料替换BOM.csv', bomCount: 15, linkedDishes: 22, success: 15, failed: 0, operator: '王经理' },
];

const fieldMappings: BomFieldMapping[] = [
  { sourceCol: '菜品编码', targetField: 'dish_code', sample: 'D001', required: true, matched: true },
  { sourceCol: '菜品名称', targetField: 'dish_name', sample: '招牌剁椒鱼头', required: true, matched: true },
  { sourceCol: '原料编码', targetField: 'ingredient_code', sample: 'I042', required: true, matched: true },
  { sourceCol: '原料名称', targetField: 'ingredient_name', sample: '新鲜草鱼', required: true, matched: true },
  { sourceCol: '用量', targetField: 'quantity', sample: '500', required: true, matched: true },
  { sourceCol: '单位', targetField: 'unit', sample: 'g', required: true, matched: true },
  { sourceCol: '损耗系数', targetField: 'waste_ratio', sample: '0.05', required: false, matched: false },
  { sourceCol: '成本单价', targetField: 'cost_per_unit', sample: '12.80', required: false, matched: true },
];

const previewRows: BomPreviewRow[] = [
  { dishCode: 'D001', dishName: '招牌剁椒鱼头', ingredient: '新鲜草鱼', quantity: 500, unit: 'g', costPerUnit: '¥12.80/kg' },
  { dishCode: 'D001', dishName: '招牌剁椒鱼头', ingredient: '剁椒', quantity: 80, unit: 'g', costPerUnit: '¥28.00/kg' },
  { dishCode: 'D001', dishName: '招牌剁椒鱼头', ingredient: '豆豉', quantity: 20, unit: 'g', costPerUnit: '¥15.00/kg' },
  { dishCode: 'D023', dishName: '夫妻肺片', ingredient: '牛肉', quantity: 150, unit: 'g', costPerUnit: '¥85.00/kg' },
  { dishCode: 'D023', dishName: '夫妻肺片', ingredient: '牛肚', quantity: 100, unit: 'g', costPerUnit: '¥42.00/kg' },
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
    render: (v: number) => <span className={styles.successNum}>{v}</span>,
  },
  {
    key: 'failed', dataIndex: 'failed', title: '失败', width: 70, align: 'right',
    render: (v: number) => (
      v > 0 ? <ZBadge type="critical" text={String(v)} /> : <span className={styles.zeroNum}>{v}</span>
    ),
  },
  { key: 'operator', dataIndex: 'operator', title: '操作人', width: 100 },
];

const mappingColumns: ZTableColumn<BomFieldMapping>[] = [
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

const previewColumns: ZTableColumn<BomPreviewRow>[] = [
  { key: 'dishCode', dataIndex: 'dishCode', title: '菜品编码', width: 100 },
  { key: 'dishName', dataIndex: 'dishName', title: '菜品名称' },
  { key: 'ingredient', dataIndex: 'ingredient', title: '原料名称' },
  { key: 'quantity', dataIndex: 'quantity', title: '用量', width: 80, align: 'right' },
  { key: 'unit', dataIndex: 'unit', title: '单位', width: 60, align: 'center' },
  { key: 'costPerUnit', dataIndex: 'costPerUnit', title: '成本单价', width: 120, align: 'right' },
];

/* ── 页面组件 ── */

const BomImportPage: React.FC = () => {
  const [currentStep] = useState(0);
  const [dragOver, setDragOver] = useState(false);

  const totalBom = importHistory.reduce((s, r) => s + r.bomCount, 0);
  const totalFailed = importHistory.reduce((s, r) => s + r.failed, 0);
  const successRate = Math.round(((totalBom - totalFailed) / totalBom) * 100);
  const unmappedCount = fieldMappings.filter(f => !f.matched).length;

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <div className={styles.headerLeft}>
          <h1 className={styles.title}>BOM导入</h1>
          <p className={styles.subtitle}>批量导入物料清单数据，支持版本管理、损耗系数与成本计算</p>
        </div>
        <ZButton variant="ghost" size="sm">下载BOM模板</ZButton>
      </div>

      {/* KPI 摘要 */}
      <div className={styles.kpiRow}>
        <ZCard><ZKpi label="历史导入BOM总数" value={totalBom} changeLabel="条" /></ZCard>
        <ZCard><ZKpi label="本月导入次数" value={3} changeLabel="次" /></ZCard>
        <ZCard><ZKpi label="BOM成功率" value={successRate} unit="%" change={1.2} changeLabel="较上月" /></ZCard>
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
        <ZCard title="上传BOM文件">
          <div
            className={`${styles.uploadZone} ${dragOver ? styles.uploadZoneDragOver : ''}`}
            onDragOver={e => { e.preventDefault(); setDragOver(true); }}
            onDragLeave={() => setDragOver(false)}
            onDrop={e => { e.preventDefault(); setDragOver(false); }}
          >
            <div className={styles.uploadIcon}>📋</div>
            <p className={styles.uploadTitle}>点击或拖拽BOM文件到此区域</p>
            <p className={styles.uploadHint}>支持 .xlsx / .csv 格式，单次最大 10MB</p>
            <p className={styles.uploadHint}>必填列：菜品编码、原料名称、用量、单位</p>
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
          {unmappedCount > 0 && (
            <div className={styles.mappingHint}>
              <ZBadge type="warning" text={`${unmappedCount}个字段未映射`} />
              <span className={styles.mappingHintText}>「损耗系数」列未能自动匹配，将使用系统默认值 0.03</span>
            </div>
          )}
          {/* TODO: GET /api/v1/ops/bom-import/field-mapping */}
          <ZTable<BomFieldMapping> columns={mappingColumns} data={fieldMappings} rowKey="sourceCol" />
        </ZCard>
      </div>

      {/* 数据预览 */}
      <div className={styles.section}>
        <ZCard title="数据预览（前5行）">
          <div className={styles.previewNote}>
            <ZBadge type="info" text="预览" />
            <span className={styles.previewNoteText}>共识别 38 条BOM记录，关联 45 个菜品，以下显示前5行</span>
          </div>
          {/* TODO: GET /api/v1/ops/bom-import/preview */}
          <ZTable<BomPreviewRow> columns={previewColumns} data={previewRows} rowKey="ingredient" />
        </ZCard>
      </div>

      {/* 导入历史 */}
      <div className={styles.section}>
        <ZCard title="导入历史">
          {/* TODO: GET /api/v1/ops/bom-import-history */}
          <ZTable<BomImportRecord> columns={historyColumns} data={importHistory} rowKey="time" />
        </ZCard>
      </div>
    </div>
  );
};

export default BomImportPage;
