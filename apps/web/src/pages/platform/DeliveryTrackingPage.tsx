import React from 'react';
import { ZCard, ZBadge, ZKpi } from '../../design-system/components';
import type { ZTableColumn } from '../../design-system/components';
import ZTable from '../../design-system/components/ZTable';
import styles from './DeliveryTrackingPage.module.css';

// ── 类型 ─────────────────────────────────────────────────────────────────────

interface DeliveryItem {
  id: string;
  merchantName: string;
  currentStage: string;
  startDate: string;
  estimatedLaunch: string;
  blocker: string;
  owner: string;
}

// ── Mock 数据 ────────────────────────────────────────────────────────────────

const MOCK_DELIVERIES: DeliveryItem[] = [
  { id: 'D001', merchantName: '尝在一起', currentStage: '测试中', startDate: '2026-01-15', estimatedLaunch: '2026-03-30', blocker: '无', owner: '张工' },
  { id: 'D002', merchantName: '徐记海鲜', currentStage: '已上线', startDate: '2025-11-01', estimatedLaunch: '2026-02-01', blocker: '无', owner: '李工' },
  { id: 'D003', merchantName: '最黔线', currentStage: '接入中', startDate: '2026-02-20', estimatedLaunch: '2026-04-15', blocker: 'POS API 对接', owner: '王工' },
  { id: 'D004', merchantName: '尚宫厨', currentStage: '接入中', startDate: '2026-03-01', estimatedLaunch: '2026-05-01', blocker: '合同确认', owner: '赵工' },
  { id: 'D005', merchantName: '湘味轩', currentStage: '配置中', startDate: '2026-02-10', estimatedLaunch: '2026-04-01', blocker: '无', owner: '陈工' },
  { id: 'D006', merchantName: '辣小二', currentStage: '配置中', startDate: '2026-02-15', estimatedLaunch: '2026-04-10', blocker: '菜品数据缺失', owner: '刘工' },
];

// ── 组件 ─────────────────────────────────────────────────────────────────────

const DeliveryTrackingPage: React.FC = () => {
  const columns: ZTableColumn<DeliveryItem>[] = [
    { key: 'merchantName', dataIndex: 'merchantName', title: '商户名' },
    { key: 'currentStage', dataIndex: 'currentStage', title: '当前阶段',
      render: (v: string) => {
        const typeMap: Record<string, 'info' | 'warning' | 'accent' | 'success'> = {
          '接入中': 'info', '配置中': 'warning', '测试中': 'accent', '已上线': 'success',
        };
        return <ZBadge type={typeMap[v] || 'default'} text={v} />;
      },
    },
    { key: 'startDate', dataIndex: 'startDate', title: '开始日期' },
    { key: 'estimatedLaunch', dataIndex: 'estimatedLaunch', title: '预计上线' },
    { key: 'blocker', dataIndex: 'blocker', title: '阻塞项',
      render: (v: string) => v !== '无' ? <span className={styles.blockerCell}>{v}</span> : <span>无</span>,
    },
    { key: 'owner', dataIndex: 'owner', title: '负责人' },
  ];

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <h2>交付跟踪</h2>
        <p>客户交付进度与 SLA 达成情况追踪</p>
      </div>

      {/* 阶段统计 KPI */}
      <div className={styles.kpiRow}>
        <ZCard><ZKpi label="接入中" value={3} color="var(--accent, #FF6B2C)" /></ZCard>
        <ZCard><ZKpi label="配置中" value={2} /></ZCard>
        <ZCard><ZKpi label="测试中" value={1} /></ZCard>
        <ZCard><ZKpi label="已上线" value={8} color="#22c55e" /></ZCard>
      </div>

      {/* 商户交付进度 */}
      <div className={styles.section}>
        <div className={styles.sectionTitle}>商户交付进度</div>
        <ZCard noPadding>
          <ZTable<DeliveryItem>
            columns={columns}
            dataSource={MOCK_DELIVERIES}
            rowKey="id"
          />
        </ZCard>
      </div>
    </div>
  );
};

export default DeliveryTrackingPage;
