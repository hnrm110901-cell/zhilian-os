import React from 'react';
import { ZCard, ZBadge } from '../../design-system/components';
import type { ZTableColumn } from '../../design-system/components';
import ZTable from '../../design-system/components/ZTable';
import styles from './RenewalAlertPage.module.css';

// ── 类型 ─────────────────────────────────────────────────────────────────────

interface RenewalItem {
  id: string;
  merchantName: string;
  contractExpiry: string;
  usageFreq: string;
  satisfaction: string;
  riskLevel: string;
  renewalProb: string;
}

// ── Mock 数据 ────────────────────────────────────────────────────────────────

const MOCK_RENEWALS: RenewalItem[] = [
  { id: 'R001', merchantName: '麻辣香锅坊', contractExpiry: '2026-04-10', usageFreq: '高', satisfaction: '4.5/5', riskLevel: '低', renewalProb: '95%' },
  { id: 'R002', merchantName: '川香阁', contractExpiry: '2026-04-25', usageFreq: '中', satisfaction: '3.8/5', riskLevel: '中', renewalProb: '72%' },
  { id: 'R003', merchantName: '粤式茶餐厅', contractExpiry: '2026-05-01', usageFreq: '低', satisfaction: '3.2/5', riskLevel: '高', renewalProb: '45%' },
  { id: 'R004', merchantName: '江南小厨', contractExpiry: '2026-05-15', usageFreq: '高', satisfaction: '4.8/5', riskLevel: '低', renewalProb: '98%' },
  { id: 'R005', merchantName: '鲁菜馆', contractExpiry: '2026-05-20', usageFreq: '中', satisfaction: '3.5/5', riskLevel: '中', renewalProb: '68%' },
  { id: 'R006', merchantName: '西北风味', contractExpiry: '2026-06-01', usageFreq: '高', satisfaction: '4.2/5', riskLevel: '低', renewalProb: '88%' },
  { id: 'R007', merchantName: '东北饺子王', contractExpiry: '2026-06-10', usageFreq: '低', satisfaction: '2.8/5', riskLevel: '高', renewalProb: '35%' },
  { id: 'R008', merchantName: '闽南小吃', contractExpiry: '2026-06-15', usageFreq: '中', satisfaction: '4.0/5', riskLevel: '低', renewalProb: '82%' },
];

// ── 组件 ─────────────────────────────────────────────────────────────────────

const RenewalAlertPage: React.FC = () => {
  const columns: ZTableColumn<RenewalItem>[] = [
    { key: 'merchantName', dataIndex: 'merchantName', title: '商户名' },
    { key: 'contractExpiry', dataIndex: 'contractExpiry', title: '合同到期日' },
    { key: 'usageFreq', dataIndex: 'usageFreq', title: '使用频率' },
    { key: 'satisfaction', dataIndex: 'satisfaction', title: '满意度' },
    { key: 'riskLevel', dataIndex: 'riskLevel', title: '风险等级',
      render: (v: string) => {
        const typeMap: Record<string, 'error' | 'warning' | 'success'> = {
          '高': 'error', '中': 'warning', '低': 'success',
        };
        return <ZBadge type={typeMap[v] || 'default'} text={v} />;
      },
    },
    { key: 'renewalProb', dataIndex: 'renewalProb', title: '续费概率', align: 'center',
      render: (v: string) => {
        const num = parseInt(v);
        const cls = num >= 80 ? styles.riskLow : num >= 60 ? styles.riskMid : styles.riskHigh;
        return <span className={`${styles.probCell} ${cls}`}>{v}</span>;
      },
    },
    { key: 'actions', title: '操作',
      render: () => <button className={styles.actionBtn}>跟进</button>,
    },
  ];

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <h2>续费预警</h2>
        <p>商户合同到期提醒、续费跟踪、流失预警分析</p>
      </div>

      {/* 分组卡片 */}
      <div className={styles.section}>
        <div className={styles.sectionTitle}>到期预警概览</div>
        <div className={styles.cardGrid}>
          <ZCard className={styles.alertCard}>
            <div className={`${styles.alertCardNum} ${styles.alertCardRed}`}>2</div>
            <div className={styles.alertCardLabel}>30天内到期</div>
          </ZCard>
          <ZCard className={styles.alertCard}>
            <div className={`${styles.alertCardNum} ${styles.alertCardOrange}`}>3</div>
            <div className={styles.alertCardLabel}>60天内到期</div>
          </ZCard>
          <ZCard className={styles.alertCard}>
            <div className={`${styles.alertCardNum} ${styles.alertCardYellow}`}>3</div>
            <div className={styles.alertCardLabel}>90天内到期</div>
          </ZCard>
        </div>
      </div>

      {/* 续费列表 */}
      <div className={styles.section}>
        <div className={styles.sectionTitle}>续费列表</div>
        <ZCard noPadding>
          <ZTable<RenewalItem>
            columns={columns}
            dataSource={MOCK_RENEWALS}
            rowKey="id"
          />
        </ZCard>
      </div>
    </div>
  );
};

export default RenewalAlertPage;
