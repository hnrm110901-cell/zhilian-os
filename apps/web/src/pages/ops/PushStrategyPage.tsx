import React from 'react';
import { ZCard, ZBadge, ZKpi } from '../../design-system/components';
import type { ZTableColumn } from '../../design-system/components';
import ZTable from '../../design-system/components/ZTable';
import styles from './PushStrategyPage.module.css';

// ── 类型 ─────────────────────────────────────────────────────────────────────

interface Strategy {
  id: string;
  name: string;
  channel: string;
  trigger: string;
  priority: string;
  silentPeriod: string;
  dailyLimit: number;
  enabled: boolean;
}

// ── Mock 数据 ────────────────────────────────────────────────────────────────

const MOCK_STRATEGIES: Strategy[] = [
  { id: 'S001', name: '库存预警推送', channel: '企业微信', trigger: '库存低于安全线', priority: '高', silentPeriod: '22:00-07:00', dailyLimit: 5, enabled: true },
  { id: 'S002', name: '日结提醒', channel: '企业微信', trigger: '每日22:30', priority: '中', silentPeriod: '无', dailyLimit: 1, enabled: true },
  { id: 'S003', name: 'AI决策建议', channel: '企业微信+短信', trigger: '决策置信度>80%', priority: '高', silentPeriod: '23:00-06:00', dailyLimit: 10, enabled: true },
  { id: 'S004', name: '排班变更通知', channel: '企业微信', trigger: '排班变更', priority: '中', silentPeriod: '22:00-07:00', dailyLimit: 8, enabled: true },
  { id: 'S005', name: '设备离线告警', channel: '短信+企业微信', trigger: '设备离线>5min', priority: '紧急', silentPeriod: '无', dailyLimit: 20, enabled: false },
  { id: 'S006', name: '会员流失预警', channel: '企业微信', trigger: 'RFM降级', priority: '低', silentPeriod: '21:00-08:00', dailyLimit: 3, enabled: true },
];

// ── 组件 ─────────────────────────────────────────────────────────────────────

const PushStrategyPage: React.FC = () => {
  const columns: ZTableColumn<Strategy>[] = [
    { key: 'name', dataIndex: 'name', title: '策略名称' },
    { key: 'channel', dataIndex: 'channel', title: '渠道' },
    { key: 'trigger', dataIndex: 'trigger', title: '触发条件' },
    { key: 'priority', dataIndex: 'priority', title: '优先级',
      render: (v: string) => {
        const typeMap: Record<string, 'error' | 'warning' | 'info' | 'default'> = {
          '紧急': 'error', '高': 'warning', '中': 'info', '低': 'default',
        };
        return <ZBadge type={typeMap[v] || 'default'} text={v} />;
      },
    },
    { key: 'silentPeriod', dataIndex: 'silentPeriod', title: '静默时段' },
    { key: 'dailyLimit', dataIndex: 'dailyLimit', title: '日上限', align: 'center' },
    { key: 'enabled', dataIndex: 'enabled', title: '状态',
      render: (v: boolean) => (
        <label className={styles.toggle}>
          <input type="checkbox" defaultChecked={v} />
          <span className={styles.toggleTrack} />
        </label>
      ),
    },
  ];

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <h2>推送策略</h2>
        <p>通知推送策略配置，管理推送渠道、频率与智能触达规则</p>
      </div>

      {/* 推送效果 KPI */}
      <div className={styles.kpiRow}>
        <ZCard><ZKpi label="送达率" value="98.5" unit="%" status="good" change={0.3} changeLabel="较上周" /></ZCard>
        <ZCard><ZKpi label="打开率" value="32.1" unit="%" change={2.5} changeLabel="较上周" /></ZCard>
        <ZCard><ZKpi label="点击率" value="15.8" unit="%" change={1.2} changeLabel="较上周" /></ZCard>
      </div>

      {/* 策略列表 */}
      <div className={styles.section}>
        <div className={styles.sectionTitle}>策略列表</div>
        <ZCard noPadding>
          <ZTable<Strategy>
            columns={columns}
            dataSource={MOCK_STRATEGIES}
            rowKey="id"
          />
        </ZCard>
      </div>
    </div>
  );
};

export default PushStrategyPage;
