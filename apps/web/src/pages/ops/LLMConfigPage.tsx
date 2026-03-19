import React, { useState } from 'react';
import { ZCard, ZBadge, ZKpi } from '../../design-system/components';
import type { ZTableColumn } from '../../design-system/components';
import ZTable from '../../design-system/components/ZTable';
import styles from './LLMConfigPage.module.css';

// TODO: GET /api/v1/ops/llm-config/providers
// TODO: GET /api/v1/ops/llm-config/api-keys
// TODO: GET /api/v1/ops/llm-config/usage-stats

// ── 类型 ─────────────────────────────────────────────────────────────────────

interface Provider {
  id: string;
  name: string;
  status: 'active' | 'standby' | 'disabled';
  model: string;
  temperature: number;
  maxTokens: number;
  dailyCalls: number;
  avgLatency: number;
  errorRate: number;
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
  {
    id: 'claude',
    name: 'Claude',
    status: 'active',
    model: 'claude-3-opus',
    temperature: 0.3,
    maxTokens: 4096,
    dailyCalls: 820,
    avgLatency: 920,
    errorRate: 0.2,
  },
  {
    id: 'deepseek',
    name: 'DeepSeek',
    status: 'active',
    model: 'deepseek-v3',
    temperature: 0.5,
    maxTokens: 4096,
    dailyCalls: 310,
    avgLatency: 480,
    errorRate: 0.4,
  },
  {
    id: 'openai',
    name: 'OpenAI',
    status: 'standby',
    model: 'gpt-4o',
    temperature: 0.4,
    maxTokens: 4096,
    dailyCalls: 120,
    avgLatency: 1050,
    errorRate: 0.8,
  },
];

const MOCK_KEYS: ApiKey[] = [
  { id: 'K001', provider: 'Claude', maskedKey: 'sk-ant-***...8f2a', createdAt: '2026-01-10', status: '正常' },
  { id: 'K002', provider: 'DeepSeek', maskedKey: 'sk-ds-***...c3b1', createdAt: '2026-01-15', status: '正常' },
  { id: 'K003', provider: 'OpenAI', maskedKey: 'sk-***...9d4e', createdAt: '2026-02-01', status: '正常' },
  { id: 'K004', provider: 'Claude', maskedKey: 'sk-ant-***...1a7c', createdAt: '2025-12-20', status: '已过期' },
];

// ── 组件 ─────────────────────────────────────────────────────────────────────

const statusLabel: Record<Provider['status'], string> = {
  active: '主力',
  standby: '备用',
  disabled: '已禁用',
};

const statusType: Record<Provider['status'], 'success' | 'warning' | 'default'> = {
  active: 'success',
  standby: 'warning',
  disabled: 'default',
};

const LLMConfigPage: React.FC = () => {
  const [selectedProvider, setSelectedProvider] = useState<Provider>(PROVIDERS[0]);

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
    { key: 'actions', title: '操作',
      render: () => (
        <div className={styles.actionGroup}>
          <button className={styles.actionBtn}>轮换</button>
          <button className={`${styles.actionBtn} ${styles.actionBtnDanger}`}>吊销</button>
        </div>
      ),
    },
  ];

  const totalCalls = PROVIDERS.reduce((s, p) => s + p.dailyCalls, 0);

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <h2>LLM 配置</h2>
        <p>为商户配置 LLM 模型选型，平衡成本与效果</p>
      </div>

      {/* 今日汇总 KPI */}
      <div className={styles.kpiRow}>
        <ZCard><ZKpi label="今日调用次数" value={totalCalls} change={5.2} changeLabel="较昨日" /></ZCard>
        <ZCard><ZKpi label="今日 Tokens" value="12.5K" change={3.1} changeLabel="较昨日" /></ZCard>
        <ZCard><ZKpi label="平均响应延迟" value="820" unit="ms" change={-4.2} changeLabel="较昨日" /></ZCard>
        <ZCard><ZKpi label="综合错误率" value="0.4" unit="%" status="good" /></ZCard>
      </div>

      {/* Provider 卡片 */}
      <div className={styles.section}>
        <div className={styles.sectionTitle}>Provider 配置</div>
        <div className={styles.cardGrid}>
          {PROVIDERS.map((p) => (
            <ZCard
              key={p.id}
              className={`${styles.providerCard} ${selectedProvider.id === p.id ? styles.providerCardActive : ''}`}
              onClick={() => setSelectedProvider(p)}
            >
              <div className={styles.providerHeader}>
                <span className={styles.providerName}>{p.name}</span>
                <ZBadge type={statusType[p.status]} text={statusLabel[p.status]} />
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
                  <span className={styles.providerLabel}>Max Tokens</span>
                  <span className={styles.providerValue}>{p.maxTokens.toLocaleString()}</span>
                </div>
              </div>
              <div className={styles.providerStats}>
                <div className={styles.statItem}>
                  <span className={styles.statVal}>{p.dailyCalls}</span>
                  <span className={styles.statLbl}>今日调用</span>
                </div>
                <div className={styles.statItem}>
                  <span className={styles.statVal}>{p.avgLatency}ms</span>
                  <span className={styles.statLbl}>平均延迟</span>
                </div>
                <div className={styles.statItem}>
                  <span className={`${styles.statVal} ${p.errorRate > 0.5 ? styles.statErr : styles.statOk}`}>{p.errorRate}%</span>
                  <span className={styles.statLbl}>错误率</span>
                </div>
              </div>
            </ZCard>
          ))}
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
