import React, { useState } from 'react';
import { ZCard, ZBadge, ZKpi } from '../../design-system/components';
import type { ZTableColumn } from '../../design-system/components';
import ZTable from '../../design-system/components/ZTable';
import styles from './PushStrategyPage.module.css';

// TODO: GET /api/v1/ops/push-strategy/list
// TODO: GET /api/v1/ops/push-strategy/analytics

// ── 类型 ─────────────────────────────────────────────────────────────────────

interface Strategy {
  id: string;
  name: string;
  channel: string;
  trigger: string;
  priority: string;
  silentPeriod: string;
  dailyLimit: number;
  deliveryRate: number;
  openRate: number;
  enabled: boolean;
}

// ── Mock 数据 ────────────────────────────────────────────────────────────────

const MOCK_STRATEGIES: Strategy[] = [
  { id: 'S001', name: '库存预警推送', channel: '企业微信', trigger: '库存低于安全线', priority: '高', silentPeriod: '22:00-07:00', dailyLimit: 5, deliveryRate: 99.2, openRate: 78.4, enabled: true },
  { id: 'S002', name: '日结提醒', channel: '企业微信', trigger: '每日 22:30', priority: '中', silentPeriod: '无', dailyLimit: 1, deliveryRate: 100, openRate: 91.2, enabled: true },
  { id: 'S003', name: 'AI决策建议', channel: '企业微信+短信', trigger: '决策置信度>80%', priority: '高', silentPeriod: '23:00-06:00', dailyLimit: 10, deliveryRate: 97.8, openRate: 45.3, enabled: true },
  { id: 'S004', name: '排班变更通知', channel: '企业微信', trigger: '排班变更', priority: '中', silentPeriod: '22:00-07:00', dailyLimit: 8, deliveryRate: 98.5, openRate: 65.1, enabled: true },
  { id: 'S005', name: '设备离线告警', channel: '短信+企业微信', trigger: '设备离线>5min', priority: '紧急', silentPeriod: '无', dailyLimit: 20, deliveryRate: 99.8, openRate: 88.7, enabled: false },
  { id: 'S006', name: '会员流失预警', channel: '企业微信', trigger: 'RFM降级', priority: '低', silentPeriod: '21:00-08:00', dailyLimit: 3, deliveryRate: 96.3, openRate: 22.5, enabled: true },
];

// ── 组件 ─────────────────────────────────────────────────────────────────────

const PushStrategyPage: React.FC = () => {
  const [strategies, setStrategies] = useState<Strategy[]>(MOCK_STRATEGIES);

  const toggleStrategy = (id: string) => {
    setStrategies((prev) =>
      prev.map((s) => s.id === id ? { ...s, enabled: !s.enabled } : s),
    );
  };

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
    { key: 'deliveryRate', dataIndex: 'deliveryRate', title: '送达率', align: 'center',
      render: (v: number) => <span className={styles.rateCell}>{v}%</span>,
    },
    { key: 'openRate', dataIndex: 'openRate', title: '打开率', align: 'center',
      render: (v: number) => <span className={styles.rateCell}>{v}%</span>,
    },
    { key: 'enabled', dataIndex: 'enabled', title: '启用',
      render: (v: boolean, row: Strategy) => (
        <label className={styles.toggle}>
          <input
            type="checkbox"
            checked={v}
            onChange={() => toggleStrategy(row.id)}
          />
          <span className={styles.toggleTrack} />
        </label>
      ),
    },
  ];

  const enabledCount = strategies.filter((s) => s.enabled).length;
  const avgDelivery = (strategies.filter((s) => s.enabled).reduce((sum, s) => sum + s.deliveryRate, 0) / enabledCount).toFixed(1);
  const avgOpen = (strategies.filter((s) => s.enabled).reduce((sum, s) => sum + s.openRate, 0) / enabledCount).toFixed(1);

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <h2>推送策略</h2>
        <p>通知推送策略配置，管理推送渠道、频率与智能触达规则</p>
      </div>

      {/* 推送效果 KPI */}
      <div className={styles.kpiRow}>
        <ZCard><ZKpi label="已启用策略" value={enabledCount} unit="个" /></ZCard>
        <ZCard><ZKpi label="综合送达率" value={avgDelivery} unit="%" status="good" change={0.3} changeLabel="较上周" /></ZCard>
        <ZCard><ZKpi label="综合打开率" value={avgOpen} unit="%" change={2.5} changeLabel="较上周" /></ZCard>
        <ZCard><ZKpi label="今日推送次数" value="248" change={12.3} changeLabel="较昨日" /></ZCard>
      </div>

      {/* 推送分析 */}
      <div className={styles.section}>
        <div className={styles.sectionTitle}>渠道分析</div>
        <div className={styles.analyticsRow}>
          <ZCard className={styles.analyticsCard}>
            <div className={styles.analyticsTitle}>企业微信</div>
            <div className={styles.analyticsGrid}>
              <div className={styles.analyticsStat}>
                <span className={styles.analyticsVal}>98.5%</span>
                <span className={styles.analyticsLbl}>送达率</span>
              </div>
              <div className={styles.analyticsStat}>
                <span className={styles.analyticsVal}>62.3%</span>
                <span className={styles.analyticsLbl}>打开率</span>
              </div>
              <div className={styles.analyticsStat}>
                <span className={styles.analyticsVal}>28.1%</span>
                <span className={styles.analyticsLbl}>点击率</span>
              </div>
            </div>
          </ZCard>
          <ZCard className={styles.analyticsCard}>
            <div className={styles.analyticsTitle}>短信</div>
            <div className={styles.analyticsGrid}>
              <div className={styles.analyticsStat}>
                <span className={styles.analyticsVal}>99.2%</span>
                <span className={styles.analyticsLbl}>送达率</span>
              </div>
              <div className={styles.analyticsStat}>
                <span className={styles.analyticsVal}>—</span>
                <span className={styles.analyticsLbl}>打开率</span>
              </div>
              <div className={styles.analyticsStat}>
                <span className={styles.analyticsVal}>8.4%</span>
                <span className={styles.analyticsLbl}>链接点击率</span>
              </div>
            </div>
          </ZCard>
        </div>
      </div>

      {/* 策略列表 */}
      <div className={styles.section}>
        <div className={styles.sectionTitle}>策略列表</div>
        <ZCard noPadding>
          <ZTable<Strategy>
            columns={columns}
            dataSource={strategies}
            rowKey="id"
          />
        </ZCard>
      </div>
    </div>
  );
};

export default PushStrategyPage;
