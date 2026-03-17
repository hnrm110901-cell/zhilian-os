import React from 'react';
import { ZCard, ZBadge } from '../../design-system/components';
import type { ZTableColumn } from '../../design-system/components';
import ZTable from '../../design-system/components/ZTable';
import styles from './AgentTrainingPage.module.css';

// ── 类型 ─────────────────────────────────────────────────────────────────────

interface TrainingTask {
  id: string;
  agentName: string;
  dataSource: string;
  sampleCount: number;
  accuracy: number;
  status: string;
  lastTrained: string;
}

// ── Mock 数据 ────────────────────────────────────────────────────────────────

const MOCK_TASKS: TrainingTask[] = [
  { id: 'T001', agentName: 'ScheduleAgent', dataSource: '排班历史记录', sampleCount: 12500, accuracy: 94.2, status: '已完成', lastTrained: '2026-03-16 02:00' },
  { id: 'T002', agentName: 'InventoryAgent', dataSource: '库存流水+盘点', sampleCount: 28000, accuracy: 91.8, status: '已完成', lastTrained: '2026-03-15 02:00' },
  { id: 'T003', agentName: 'OrderAgent', dataSource: '订单明细', sampleCount: 45000, accuracy: 96.1, status: '已完成', lastTrained: '2026-03-16 02:00' },
  { id: 'T004', agentName: 'PerformanceAgent', dataSource: 'KPI日快照', sampleCount: 8200, accuracy: 89.5, status: '训练中', lastTrained: '2026-03-17 02:00' },
  { id: 'T005', agentName: 'DecisionAgent', dataSource: '决策日志', sampleCount: 3600, accuracy: 87.3, status: '已完成', lastTrained: '2026-03-14 02:00' },
  { id: 'T006', agentName: 'ServiceAgent', dataSource: '服务评价+工单', sampleCount: 15800, accuracy: 92.7, status: '已完成', lastTrained: '2026-03-15 02:00' },
  { id: 'T007', agentName: 'PrivateDomainAgent', dataSource: '会员行为日志', sampleCount: 52000, accuracy: 90.4, status: '排队中', lastTrained: '2026-03-13 02:00' },
  { id: 'T008', agentName: 'SupplierAgent', dataSource: '采购单+供应商', sampleCount: 6800, accuracy: 88.1, status: '已完成', lastTrained: '2026-03-16 02:00' },
];

// ── 组件 ─────────────────────────────────────────────────────────────────────

const AgentTrainingPage: React.FC = () => {
  const columns: ZTableColumn<TrainingTask>[] = [
    { key: 'agentName', dataIndex: 'agentName', title: 'Agent名称' },
    { key: 'dataSource', dataIndex: 'dataSource', title: '数据源' },
    { key: 'sampleCount', dataIndex: 'sampleCount', title: '样本数', align: 'right',
      render: (v: number) => v.toLocaleString(),
    },
    { key: 'accuracy', dataIndex: 'accuracy', title: '当前准确率', align: 'center',
      render: (v: number) => {
        const cls = v >= 92 ? styles.accuracyHigh : v >= 88 ? styles.accuracyMid : styles.accuracyLow;
        return <span className={cls}>{v}%</span>;
      },
    },
    { key: 'status', dataIndex: 'status', title: '状态',
      render: (v: string) => {
        const typeMap: Record<string, 'success' | 'warning' | 'info'> = {
          '已完成': 'success', '训练中': 'warning', '排队中': 'info',
        };
        return <ZBadge type={typeMap[v] || 'default'} text={v} />;
      },
    },
    { key: 'lastTrained', dataIndex: 'lastTrained', title: '最后训练' },
  ];

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <div>
          <h2>Agent 训练数据</h2>
          <p>AI Agent 训练任务管理，配置训练数据集与评估指标</p>
        </div>
      </div>

      <div className={styles.section}>
        <div className={styles.sectionTitle}>训练任务列表</div>
        <ZCard noPadding>
          <ZTable<TrainingTask>
            columns={columns}
            dataSource={MOCK_TASKS}
            rowKey="id"
          />
        </ZCard>
      </div>

      <div className={styles.section}>
        <div className={styles.sectionTitle}>样本审核面板</div>
        <ZCard title="样本审核">
          <div className={styles.reviewPanel}>
            选择一个训练任务以查看和审核样本数据
          </div>
        </ZCard>
      </div>
    </div>
  );
};

export default AgentTrainingPage;
