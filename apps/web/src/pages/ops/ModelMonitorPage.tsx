import React from 'react';
import { ZCard, ZBadge, ZKpi } from '../../design-system/components';
import type { ZTableColumn } from '../../design-system/components';
import ZTable from '../../design-system/components/ZTable';
import styles from './ModelMonitorPage.module.css';

// TODO: GET /api/v1/ops/model-monitor/health
// TODO: GET /api/v1/ops/model-monitor/call-traces

// ── 类型 ─────────────────────────────────────────────────────────────────────

interface HealthCard {
  key: string;
  label: string;
  score: number;
  status: 'good' | 'warning' | 'error';
  detail: string;
}

interface CallLog {
  id: string;
  time: string;
  agent: string;
  model: string;
  inputTokens: number;
  outputTokens: number;
  latency: number;
  status: string;
}

interface ErrorLog {
  id: string;
  time: string;
  agent: string;
  errorType: string;
  message: string;
}

// ── Mock 数据 ────────────────────────────────────────────────────────────────

const HEALTH_CARDS: HealthCard[] = [
  {
    key: 'embedding',
    label: '嵌入模型',
    score: 98,
    status: 'good',
    detail: 'sentence-transformers 本地 · 384维 · 正常',
  },
  {
    key: 'llm',
    label: 'LLM 服务',
    score: 94,
    status: 'good',
    detail: 'claude-3-opus 主力 · deepseek-v3 备用',
  },
  {
    key: 'agent',
    label: 'Agent 运行',
    score: 87,
    status: 'warning',
    detail: 'PrivateDomainAgent 排队中 · 1个Agent降级',
  },
  {
    key: 'rag',
    label: 'RAG 检索',
    score: 96,
    status: 'good',
    detail: 'Qdrant 正常 · 向量召回率 P90=91%',
  },
];

const MOCK_LOGS: CallLog[] = [
  { id: 'CL01', time: '09:15:02', agent: 'ScheduleAgent', model: 'claude-3-opus', inputTokens: 1250, outputTokens: 380, latency: 820, status: '成功' },
  { id: 'CL02', time: '09:12:30', agent: 'InventoryAgent', model: 'deepseek-v3', inputTokens: 890, outputTokens: 220, latency: 450, status: '成功' },
  { id: 'CL03', time: '09:10:15', agent: 'OrderAgent', model: 'claude-3-opus', inputTokens: 2100, outputTokens: 550, latency: 1200, status: '成功' },
  { id: 'CL04', time: '09:08:42', agent: 'PerformanceAgent', model: 'claude-3-opus', inputTokens: 3200, outputTokens: 890, latency: 1850, status: '降级' },
  { id: 'CL05', time: '09:05:18', agent: 'DecisionAgent', model: 'deepseek-v3', inputTokens: 1800, outputTokens: 420, latency: 680, status: '成功' },
  { id: 'CL06', time: '09:02:33', agent: 'ServiceAgent', model: 'gpt-4o', inputTokens: 950, outputTokens: 280, latency: 920, status: '成功' },
  { id: 'CL07', time: '08:58:11', agent: 'ScheduleAgent', model: 'claude-3-opus', inputTokens: 1100, outputTokens: 350, latency: 780, status: '成功' },
  { id: 'CL08', time: '08:55:05', agent: 'InventoryAgent', model: 'deepseek-v3', inputTokens: 760, outputTokens: 190, latency: 380, status: '成功' },
  { id: 'CL09', time: '08:50:22', agent: 'OrderAgent', model: 'claude-3-opus', inputTokens: 1980, outputTokens: 510, latency: 1100, status: '错误' },
  { id: 'CL10', time: '08:45:00', agent: 'PerformanceAgent', model: 'claude-3-opus', inputTokens: 2800, outputTokens: 720, latency: 1650, status: '成功' },
];

const MOCK_ERRORS: ErrorLog[] = [
  { id: 'E001', time: '08:50:22', agent: 'OrderAgent', errorType: 'TokenLimitExceeded', message: 'Input exceeds model context window (4096 tokens)' },
  { id: 'E002', time: '2026-03-16 23:15:08', agent: 'PrivateDomainAgent', errorType: 'RateLimitError', message: 'Rate limit hit on Claude API, falling back to DeepSeek' },
  { id: 'E003', time: '2026-03-16 22:03:41', agent: 'DecisionAgent', errorType: 'QdrantTimeout', message: 'Vector similarity search timed out after 5000ms' },
];

// ── 组件 ─────────────────────────────────────────────────────────────────────

const healthScoreColor = (status: HealthCard['status']) => {
  if (status === 'good') return styles.scoreGood;
  if (status === 'warning') return styles.scoreWarning;
  return styles.scoreError;
};

const ModelMonitorPage: React.FC = () => {
  const callColumns: ZTableColumn<CallLog>[] = [
    { key: 'time', dataIndex: 'time', title: '时间' },
    { key: 'agent', dataIndex: 'agent', title: 'Agent' },
    { key: 'model', dataIndex: 'model', title: '模型' },
    { key: 'inputTokens', dataIndex: 'inputTokens', title: '输入tokens', align: 'right',
      render: (v: number) => <span className={styles.tokenCell}>{v.toLocaleString()}</span>,
    },
    { key: 'outputTokens', dataIndex: 'outputTokens', title: '输出tokens', align: 'right',
      render: (v: number) => <span className={styles.tokenCell}>{v.toLocaleString()}</span>,
    },
    { key: 'latency', dataIndex: 'latency', title: '耗时', align: 'right',
      render: (v: number) => {
        const cls = v > 1500 ? styles.latencyHigh : v > 800 ? styles.latencyMid : styles.latencyCell;
        return <span className={cls}>{v}ms</span>;
      },
    },
    { key: 'status', dataIndex: 'status', title: '状态',
      render: (v: string) => {
        const typeMap: Record<string, 'success' | 'warning' | 'error'> = {
          '成功': 'success', '降级': 'warning', '错误': 'error',
        };
        return <ZBadge type={typeMap[v] || 'default'} text={v} />;
      },
    },
  ];

  const errorColumns: ZTableColumn<ErrorLog>[] = [
    { key: 'time', dataIndex: 'time', title: '时间' },
    { key: 'agent', dataIndex: 'agent', title: 'Agent' },
    { key: 'errorType', dataIndex: 'errorType', title: '错误类型',
      render: (v: string) => <ZBadge type="error" text={v} />,
    },
    { key: 'message', dataIndex: 'message', title: '错误信息',
      render: (v: string) => <span className={styles.errorMsg}>{v}</span>,
    },
  ];

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <h2>模型监控</h2>
        <p>AI 模型运行监控，追踪推理延迟、准确率与异常漂移</p>
      </div>

      {/* 4 个系统健康 KPI 卡片 */}
      <div className={styles.section}>
        <div className={styles.sectionTitle}>系统健康总览</div>
        <div className={styles.healthGrid}>
          {HEALTH_CARDS.map((card) => (
            <ZCard key={card.key} className={styles.healthCard}>
              <div className={styles.healthCardTop}>
                <span className={styles.healthLabel}>{card.label}</span>
                <ZBadge
                  type={card.status === 'good' ? 'success' : card.status === 'warning' ? 'warning' : 'error'}
                  text={card.status === 'good' ? '正常' : card.status === 'warning' ? '警告' : '异常'}
                />
              </div>
              <div className={`${styles.healthScore} ${healthScoreColor(card.status)}`}>
                {card.score}
              </div>
              <div className={styles.healthDetail}>{card.detail}</div>
              <div className={styles.healthBar}>
                <div
                  className={`${styles.healthBarFill} ${healthScoreColor(card.status)}`}
                  style={{ width: `${card.score}%` }}
                />
              </div>
            </ZCard>
          ))}
        </div>
      </div>

      {/* 性能 KPI 行 */}
      <div className={styles.kpiRow}>
        <ZCard><ZKpi label="准确率" value="92.3" unit="%" status="good" /></ZCard>
        <ZCard><ZKpi label="响应 P99" value="850" unit="ms" change={-3.2} changeLabel="较昨日" /></ZCard>
        <ZCard><ZKpi label="错误率" value="0.8" unit="%" status="good" /></ZCard>
        <ZCard><ZKpi label="降级次数" value={2} change={-50} changeLabel="较昨日" /></ZCard>
      </div>

      {/* 调用链日志 */}
      <div className={styles.section}>
        <div className={styles.sectionTitle}>调用链日志</div>
        <ZCard noPadding>
          <ZTable<CallLog>
            columns={callColumns}
            dataSource={MOCK_LOGS}
            rowKey="id"
          />
        </ZCard>
      </div>

      {/* 错误日志 */}
      <div className={styles.section}>
        <div className={styles.sectionTitle}>错误日志</div>
        <ZCard noPadding>
          <ZTable<ErrorLog>
            columns={errorColumns}
            dataSource={MOCK_ERRORS}
            rowKey="id"
          />
        </ZCard>
      </div>
    </div>
  );
};

export default ModelMonitorPage;
