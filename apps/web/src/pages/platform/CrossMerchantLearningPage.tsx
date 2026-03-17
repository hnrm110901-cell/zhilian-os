import React from 'react';
import { ZCard, ZBadge, ZKpi } from '../../design-system/components';
import type { ZTableColumn } from '../../design-system/components';
import ZTable from '../../design-system/components/ZTable';
import styles from './CrossMerchantLearningPage.module.css';

// ── 类型 ─────────────────────────────────────────────────────────────────────

interface FederatedTask {
  id: string;
  taskId: string;
  brands: string;
  modelType: string;
  rounds: number;
  accuracyGain: string;
  status: string;
}

// ── Mock 数据 ────────────────────────────────────────────────────────────────

const MOCK_TASKS: FederatedTask[] = [
  { id: '1', taskId: 'FL-001', brands: '尝在一起 / 徐记海鲜 / 最黔线', modelType: '需求预测', rounds: 15, accuracyGain: '+8.2%', status: '已完成' },
  { id: '2', taskId: 'FL-002', brands: '尝在一起 / 尚宫厨', modelType: '损耗预测', rounds: 12, accuracyGain: '+12.5%', status: '训练中' },
  { id: '3', taskId: 'FL-003', brands: '徐记海鲜 / 最黔线 / 尚宫厨', modelType: '排班优化', rounds: 8, accuracyGain: '+6.8%', status: '已完成' },
  { id: '4', taskId: 'FL-004', brands: '全部品牌', modelType: '价格弹性', rounds: 20, accuracyGain: '+15.1%', status: '排队中' },
  { id: '5', taskId: 'FL-005', brands: '尝在一起 / 徐记海鲜', modelType: '会员流失', rounds: 10, accuracyGain: '+9.3%', status: '已完成' },
];

// ── 组件 ─────────────────────────────────────────────────────────────────────

const CrossMerchantLearningPage: React.FC = () => {
  const columns: ZTableColumn<FederatedTask>[] = [
    { key: 'taskId', dataIndex: 'taskId', title: '任务ID' },
    { key: 'brands', dataIndex: 'brands', title: '参与品牌' },
    { key: 'modelType', dataIndex: 'modelType', title: '模型类型' },
    { key: 'rounds', dataIndex: 'rounds', title: '聚合轮次', align: 'center' },
    { key: 'accuracyGain', dataIndex: 'accuracyGain', title: '精度提升', align: 'center',
      render: (v: string) => <span style={{ color: '#22c55e', fontWeight: 600 }}>{v}</span>,
    },
    { key: 'status', dataIndex: 'status', title: '状态',
      render: (v: string) => {
        const typeMap: Record<string, 'success' | 'warning' | 'info'> = {
          '已完成': 'success', '训练中': 'warning', '排队中': 'info',
        };
        return <ZBadge type={typeMap[v] || 'default'} text={v} />;
      },
    },
  ];

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <h2>跨商户学习</h2>
        <p>隐私安全的联邦知识共享，跨品牌协同提升模型精度</p>
      </div>

      <div className={styles.kpiRow}>
        <ZCard><ZKpi label="参与品牌数" value={8} change={2} changeLabel="较上月" /></ZCard>
        <ZCard><ZKpi label="活跃模型" value={3} /></ZCard>
        <ZCard><ZKpi label="平均精度提升" value="12.5" unit="%" status="good" /></ZCard>
      </div>

      <div className={styles.section}>
        <div className={styles.sectionTitle}>联邦学习任务</div>
        <ZCard noPadding>
          <ZTable<FederatedTask>
            columns={columns}
            dataSource={MOCK_TASKS}
            rowKey="id"
          />
        </ZCard>
      </div>
    </div>
  );
};

export default CrossMerchantLearningPage;
