import React, { useState, useEffect } from 'react';
import {
  Card, Row, Col, Tabs, Table, Tag, Select, Statistic,
  Button, Empty, Spin, message, Progress, Badge, Tooltip,
} from 'antd';
import {
  ThunderboltOutlined, BulbOutlined, RiseOutlined,
  CheckOutlined, CloseOutlined, ReloadOutlined,
  FireOutlined, ExclamationCircleOutlined, InfoCircleOutlined,
} from '@ant-design/icons';
import ReactECharts from 'echarts-for-react';
import dayjs from 'dayjs';
import { apiClient, handleApiError } from '../services/api';
import styles from './FinancialRecommendationPage.module.css';

const { Option } = Select;

// ── 类型 ──────────────────────────────────────────────────────────────────

interface Recommendation {
  id: number;
  rec_type: string;
  metric: string;
  metric_label: string;
  title: string;
  description: string;
  action: string;
  expected_yuan_impact: number | null;
  confidence_pct: number | null;
  urgency: 'high' | 'medium' | 'low';
  priority_score: number | null;
  source_type: string;
  status: 'pending' | 'adopted' | 'dismissed';
  created_at: string | null;
}

interface StatItem {
  period: string;
  pending: number;
  adopted: number;
  dismissed: number;
  total: number;
  adoption_rate: number;
}

// ── 常量 ──────────────────────────────────────────────────────────────────

const URGENCY_COLOR: Record<string, string> = {
  high:   '#C53030',
  medium: '#C8923A',
  low:    '#8c8c8c',
};

const URGENCY_LABEL: Record<string, string> = {
  high: '紧急', medium: '关注', low: '参考',
};

const URGENCY_ICON: Record<string, React.ReactNode> = {
  high:   <FireOutlined />,
  medium: <ExclamationCircleOutlined />,
  low:    <InfoCircleOutlined />,
};

const REC_TYPE_LABEL: Record<string, string> = {
  anomaly_severe:   '严重异常',
  anomaly_moderate: '明显偏差',
  ranking_laggard:  '排名落后',
  forecast_decline: '预测下行',
  forecast_surge:   '预测上升',
};

const SOURCE_COLOR: Record<string, string> = {
  anomaly:  '#ff7875',
  ranking:  '#69b1ff',
  forecast: '#95de64',
};

const STATUS_COLOR: Record<string, string> = {
  pending:   'processing',
  adopted:   'success',
  dismissed: 'default',
};

// ── 主组件 ────────────────────────────────────────────────────────────────

const FinancialRecommendationPage: React.FC = () => {
  const [storeId, setStoreId] = useState(localStorage.getItem('store_id') || '');
  const [storeOptions, setStoreOptions] = useState<string[]>([]);
  const [period, setPeriod] = useState(dayjs().subtract(1, 'month').format('YYYY-MM'));
  const [statusFilter, setStatusFilter] = useState<string>('');

  useEffect(() => {
    apiClient.get<{ items: Array<{ id: string }> }>('/api/v1/stores?limit=50')
      .then(data => {
        const ids = (data.items ?? []).map((s: { id: string }) => s.id).filter(Boolean);
        if (ids.length > 0) setStoreOptions(ids);
      })
      .catch(() => { /* 保持默认门店列表 */ });
  }, []);

  const [recs, setRecs] = useState<Recommendation[]>([]);
  const [stats, setStats] = useState<StatItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [actionLoading, setActionLoading] = useState<number | null>(null);

  const periodOptions = Array.from({ length: 12 }, (_, i) =>
    dayjs().subtract(i + 1, 'month').format('YYYY-MM')
  );

  const fetchAll = async () => {
    setLoading(true);
    try {
      const url = `/api/v1/fin-rec/${storeId}?period=${period}${statusFilter ? `&status=${statusFilter}` : ''}`;
      const [recResp, statResp] = await Promise.all([
        apiClient.get(url),
        apiClient.get(`/api/v1/fin-rec/stats/${storeId}?periods=6`),
      ]);
      setRecs(recResp.data.recommendations ?? []);
      setStats(statResp.data.stats ?? []);
    } catch (err) {
      handleApiError(err);
    } finally {
      setLoading(false);
    }
  };

  const handleGenerate = async () => {
    setGenerating(true);
    try {
      const resp = await apiClient.post(`/api/v1/fin-rec/generate/${storeId}?period=${period}`);
      message.success(`生成完成：${resp.data.total_recs} 条建议`);
      await fetchAll();
    } catch (err) {
      handleApiError(err);
    } finally {
      setGenerating(false);
    }
  };

  const handleStatusUpdate = async (recId: number, newStatus: 'adopted' | 'dismissed') => {
    setActionLoading(recId);
    try {
      await apiClient.post(`/api/v1/fin-rec/${recId}/${newStatus}`);
      message.success(newStatus === 'adopted' ? '已标记为采纳' : '已标记为驳回');
      await fetchAll();
    } catch (err) {
      handleApiError(err);
    } finally {
      setActionLoading(null);
    }
  };

  useEffect(() => { fetchAll(); }, [period, statusFilter]);

  // ── 采纳率趋势图 ────────────────────────────────────────────────────────

  const trendOption = {
    tooltip: { trigger: 'axis' },
    legend: { data: ['已采纳', '已驳回', '待处理'], bottom: 0 },
    grid: { left: 40, right: 20, top: 20, bottom: 45 },
    xAxis: { type: 'category', data: stats.map((s) => s.period) },
    yAxis: { type: 'value', minInterval: 1 },
    series: [
      {
        name: '已采纳', type: 'bar', stack: 'total',
        data: stats.map((s) => s.adopted),
        itemStyle: { color: '#1A7A52' },
      },
      {
        name: '已驳回', type: 'bar', stack: 'total',
        data: stats.map((s) => s.dismissed),
        itemStyle: { color: '#bfbfbf' },
      },
      {
        name: '待处理', type: 'bar', stack: 'total',
        data: stats.map((s) => s.pending),
        itemStyle: { color: '#0AAF9A' },
      },
    ],
  };

  const adoptionRateOption = {
    tooltip: { formatter: (p: any) => `${p.name}: ${p.value}%` },
    xAxis: { type: 'category', data: stats.map((s) => s.period) },
    yAxis: { type: 'value', max: 100, name: '采纳率(%)' },
    grid: { left: 50, right: 20, top: 20, bottom: 40 },
    series: [
      {
        type: 'line', data: stats.map((s) => s.adoption_rate),
        smooth: true, symbol: 'circle', symbolSize: 7,
        itemStyle: { color: '#1A7A52' },
        lineStyle: { width: 2 },
        areaStyle: { opacity: 0.15, color: '#1A7A52' },
      },
    ],
  };

  // ── KPI ─────────────────────────────────────────────────────────────────

  const pendingRecs  = recs.filter((r) => r.status === 'pending');
  const highUrgency  = pendingRecs.filter((r) => r.urgency === 'high').length;
  const totalYuan    = recs.reduce((s, r) =>
    s + (r.expected_yuan_impact !== null ? Math.abs(r.expected_yuan_impact) : 0), 0);
  const latestAdopt  = stats.length ? stats[stats.length - 1]?.adoption_rate ?? 0 : 0;

  // ── 建议卡片列表 ─────────────────────────────────────────────────────────

  const RecCard: React.FC<{ rec: Recommendation }> = ({ rec }) => (
    <Card
      className={styles.recCard}
      style={{ borderLeft: `4px solid ${URGENCY_COLOR[rec.urgency]}` }}
      size="small"
    >
      <div className={styles.recHeader}>
        <div className={styles.recTitleRow}>
          <span style={{ color: URGENCY_COLOR[rec.urgency], marginRight: 6 }}>
            {URGENCY_ICON[rec.urgency]}
          </span>
          <strong className={styles.recTitle}>{rec.title}</strong>
        </div>
        <div className={styles.recTags}>
          <Tag color={URGENCY_COLOR[rec.urgency]}>{URGENCY_LABEL[rec.urgency]}</Tag>
          <Tag color={SOURCE_COLOR[rec.source_type] ?? '#d9d9d9'}>
            {REC_TYPE_LABEL[rec.rec_type] ?? rec.rec_type}
          </Tag>
          <Badge status={STATUS_COLOR[rec.status] as any} text={
            rec.status === 'pending' ? '待处理' :
            rec.status === 'adopted' ? '已采纳' : '已驳回'
          } />
        </div>
      </div>

      {rec.description && (
        <p className={styles.recDesc}>{rec.description}</p>
      )}

      <div className={styles.recAction}>
        <BulbOutlined style={{ color: '#faad14', marginRight: 6 }} />
        <span>{rec.action}</span>
      </div>

      <div className={styles.recFooter}>
        <div className={styles.recMeta}>
          {rec.expected_yuan_impact !== null && (
            <span className={styles.metaItem}>
              <span className={styles.metaLabel}>¥影响</span>
              <span style={{ color: rec.expected_yuan_impact < 0 ? '#C53030' : '#1A7A52', fontWeight: 600 }}>
                {rec.expected_yuan_impact < 0 ? '-' : '+'}
                ¥{Math.abs(rec.expected_yuan_impact).toLocaleString('zh-CN', { maximumFractionDigits: 0 })}
              </span>
            </span>
          )}
          {rec.confidence_pct !== null && (
            <span className={styles.metaItem}>
              <span className={styles.metaLabel}>置信度</span>
              <span>{rec.confidence_pct.toFixed(0)}%</span>
            </span>
          )}
          {rec.priority_score !== null && (
            <span className={styles.metaItem}>
              <span className={styles.metaLabel}>优先级</span>
              <Progress
                percent={rec.priority_score}
                size="small"
                strokeColor={URGENCY_COLOR[rec.urgency]}
                style={{ width: 80 }}
                showInfo={false}
              />
              <span>{rec.priority_score.toFixed(0)}</span>
            </span>
          )}
        </div>

        {rec.status === 'pending' && (
          <div className={styles.recActions}>
            <Tooltip title="标记为已采纳">
              <Button
                type="primary"
                size="small"
                icon={<CheckOutlined />}
                loading={actionLoading === rec.id}
                onClick={() => handleStatusUpdate(rec.id, 'adopted')}
              >
                采纳
              </Button>
            </Tooltip>
            <Tooltip title="驳回此建议">
              <Button
                size="small"
                icon={<CloseOutlined />}
                loading={actionLoading === rec.id}
                onClick={() => handleStatusUpdate(rec.id, 'dismissed')}
              >
                驳回
              </Button>
            </Tooltip>
          </div>
        )}
      </div>
    </Card>
  );

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <h2 className={styles.title}>财务智能建议</h2>
        <div className={styles.controls}>
          <Select value={storeId} onChange={setStoreId} style={{ width: 110 }}>
            {storeOptions.map(s => <Option key={s} value={s}>{s}</Option>)}
          </Select>
          <Select value={period} onChange={setPeriod} style={{ width: 120 }}>
            {periodOptions.map((p) => <Option key={p} value={p}>{p}</Option>)}
          </Select>
          <Select
            value={statusFilter}
            onChange={setStatusFilter}
            style={{ width: 100 }}
            placeholder="全部状态"
          >
            <Option value="">全部</Option>
            <Option value="pending">待处理</Option>
            <Option value="adopted">已采纳</Option>
            <Option value="dismissed">已驳回</Option>
          </Select>
          <Button
            type="primary"
            icon={<ReloadOutlined />}
            loading={generating}
            onClick={handleGenerate}
          >
            生成建议
          </Button>
        </div>
      </div>

      {/* KPI 卡 */}
      <Row gutter={[16, 16]} className={styles.kpiRow}>
        <Col xs={12} sm={6}>
          <Card className={styles.kpiCard}>
            <Statistic title="待处理建议" value={pendingRecs.length} suffix="条" />
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card className={styles.kpiCard} style={{ borderTop: `3px solid ${URGENCY_COLOR.high}` }}>
            <Statistic
              title="紧急建议"
              value={highUrgency}
              suffix="条"
              valueStyle={{ color: URGENCY_COLOR.high }}
              prefix={<FireOutlined />}
            />
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card className={styles.kpiCard}>
            <Statistic
              title="¥提升潜力"
              value={totalYuan > 0 ? `¥${totalYuan.toLocaleString('zh-CN', { maximumFractionDigits: 0 })}` : '—'}
              valueStyle={{ color: '#0AAF9A' }}
            />
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card className={styles.kpiCard}>
            <Statistic title="最近期采纳率" value={latestAdopt} suffix="%" precision={1} />
            <Progress percent={latestAdopt} size="small" showInfo={false} style={{ marginTop: 6 }} />
          </Card>
        </Col>
      </Row>

      <Spin spinning={loading}>
        <Tabs
          defaultActiveKey="list"
          items={[
            {
              key: 'list',
              label: `建议列表（${recs.length}）`,
              children: recs.length === 0 ? (
                <Empty description="暂无建议，点击「生成建议」开始分析" />
              ) : (
                <div className={styles.recList}>
                  {recs.map((r) => <RecCard key={r.id} rec={r} />)}
                </div>
              ),
            },
            {
              key: 'stats',
              label: '采纳追踪',
              children: (
                <Row gutter={[16, 16]}>
                  <Col xs={24} lg={14}>
                    <Card title="近6期建议状态分布" size="small">
                      {stats.length === 0 ? (
                        <Empty description="暂无数据" />
                      ) : (
                        <ReactECharts option={trendOption} style={{ height: 260 }} />
                      )}
                    </Card>
                  </Col>
                  <Col xs={24} lg={10}>
                    <Card title="采纳率趋势" size="small">
                      {stats.length === 0 ? (
                        <Empty description="暂无数据" />
                      ) : (
                        <ReactECharts option={adoptionRateOption} style={{ height: 260 }} />
                      )}
                    </Card>
                  </Col>
                </Row>
              ),
            },
          ]}
        />
      </Spin>
    </div>
  );
};

export default FinancialRecommendationPage;
