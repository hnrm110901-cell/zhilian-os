import React from 'react';
import { ZCard, ZBadge, ZKpi } from '../../design-system/components';
import type { ZTableColumn } from '../../design-system/components';
import ZTable from '../../design-system/components/ZTable';
import styles from './LLMConfigPage.module.css';

// ── 类型 ─────────────────────────────────────────────────────────────────────

interface Provider {
  name: string;
  status: string;
  model: string;
  temperature: number;
  dailyTokens: string;
}

interface ApiKey {
  id: string;
  provider: string;
  maskedKey: string;
  createdAt: string;
  status: string;
}

// ── Mock 数据 ────────────────────────────────────────────────────────────────

const PROVIDERS: Provider[] = [
  { name: 'Claude', status: '已启用', model: 'claude-3-opus', temperature: 0.3, dailyTokens: '8.2K' },
  { name: 'DeepSeek', status: '已启用', model: 'deepseek-v3', temperature: 0.5, dailyTokens: '3.1K' },
  { name: 'OpenAI', status: '备用', model: 'gpt-4o', temperature: 0.4, dailyTokens: '1.2K' },
];

const MOCK_KEYS: ApiKey[] = [
  { id: 'K001', provider: 'Claude', maskedKey: 'sk-ant-***...8f2a', createdAt: '2026-01-10', status: '正常' },
  { id: 'K002', provider: 'DeepSeek', maskedKey: 'sk-ds-***...c3b1', createdAt: '2026-01-15', status: '正常' },
  { id: 'K003', provider: 'OpenAI', maskedKey: 'sk-***...9d4e', createdAt: '2026-02-01', status: '正常' },
  { id: 'K004', provider: 'Claude', maskedKey: 'sk-ant-***...1a7c', createdAt: '2025-12-20', status: '已过期' },
];

// ── 组件 ─────────────────────────────────────────────────────────────────────

const LLMConfigPage: React.FC = () => {
  const keyColumns: ZTableColumn<ApiKey>[] = [
    { key: 'provider', dataIndex: 'provider', title: 'Provider' },
    { key: 'maskedKey', dataIndex: 'maskedKey', title: 'Key',
      render: (v: string) => <span className={styles.maskedKey}>{v}</span>,
    },
    { key: 'createdAt', dataIndex: 'createdAt', title: '创建时间' },
    { key: 'status', dataIndex: 'status', title: '状态',
      render: (v: string) => (
        <ZBadge type={v === '正常' ? 'success' : 'error'} text={v} />
      ),
    },
  ];

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <h2>LLM 配置</h2>
        <p>为商户配置 LLM 模型选型，平衡成本与效果</p>
      </div>

      {/* Provider 卡片 */}
      <div className={styles.section}>
        <div className={styles.sectionTitle}>Provider 配置</div>
        <div className={styles.cardGrid}>
          {PROVIDERS.map((p) => (
            <ZCard key={p.name} className={styles.providerCard}>
              <div className={styles.providerHeader}>
                <span className={styles.providerName}>{p.name}</span>
                <ZBadge type={p.status === '已启用' ? 'success' : 'default'} text={p.status} />
              </div>
              <div className={styles.providerDetail}>
                <div className={styles.providerRow}>
                  <span className={styles.providerLabel}>模型</span>
                  <span className={styles.providerValue}>{p.model}</span>
                </div>
                <div className={styles.providerRow}>
                  <span className={styles.providerLabel}>温度</span>
                  <span className={styles.providerValue}>{p.temperature}</span>
                </div>
                <div className={styles.providerRow}>
                  <span className={styles.providerLabel}>每日用量</span>
                  <span className={styles.providerValue}>{p.dailyTokens} tokens</span>
                </div>
              </div>
            </ZCard>
          ))}
        </div>
      </div>

      {/* 用量统计 KPI */}
      <div className={styles.section}>
        <div className={styles.sectionTitle}>用量统计</div>
        <div className={styles.kpiRow}>
          <ZCard><ZKpi label="今日 Tokens" value="12.5K" change={5.2} changeLabel="较昨日" /></ZCard>
          <ZCard><ZKpi label="估算费用" value="¥3.28" prefix="" change={-2.1} changeLabel="较昨日" /></ZCard>
          <ZCard><ZKpi label="平均响应" value="1.2" unit="s" change={-8.5} changeLabel="较昨日" /></ZCard>
        </div>
      </div>

      {/* API Key 管理 */}
      <div className={styles.section}>
        <div className={styles.sectionTitle}>API Key 管理</div>
        <ZCard noPadding>
          <ZTable<ApiKey>
            columns={keyColumns}
            dataSource={MOCK_KEYS}
            rowKey="id"
          />
        </ZCard>
      </div>
    </div>
  );
};

export default LLMConfigPage;
