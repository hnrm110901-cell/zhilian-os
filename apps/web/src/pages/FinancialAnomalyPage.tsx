import React, { useState, useEffect } from 'react';
import {
  Card, Row, Col, Tabs, Table, Tag, Button, Select,
  Statistic, Progress, Empty, Spin, message,
} from 'antd';
import {
  WarningOutlined, CheckCircleOutlined, ExclamationCircleOutlined,
  CloseCircleOutlined, ReloadOutlined,
} from '@ant-design/icons';
import ReactECharts from 'echarts-for-react';
import dayjs from 'dayjs';
import { apiClient, handleApiError } from '../services/api';
import styles from './FinancialAnomalyPage.module.css';

const { Option } = Select;

// ── 类型 ──────────────────────────────────────────────────────────────────

interface AnomalyRecord {
  metric: string;
  label: string;
  period: string;
  actual_value: number | null;
  expected_value: number | null;
  deviation_pct: number | null;
  z_score: number | null;
  severity: 'normal' | 'mild' | 'moderate' | 'severe';
  description: string;
  yuan_impact: number | null;
  resolved: boolean;
  detected_at: string | null;
}

interface TrendItem {
  period: string;
  severe: number;
  moderate: number;
  mild: number;
}

interface DetectResult {
  store_id: string;
  period: string;
  metrics_checked: number;
  anomaly_count: number;
  severity_counts: { severe: number; moderate: number; mild: number; normal: number };
  anomalies: AnomalyRecord[];
  all_results: AnomalyRecord[];
}

// ── 常量 ──────────────────────────────────────────────────────────────────

const SEVERITY_COLOR: Record<string, string> = {
  severe:   '#C53030',
  moderate: '#C8923A',
  mild:     '#fadb14',
  normal:   '#1A7A52',
};

const SEVERITY_LABEL: Record<string, string> = {
  severe: '严重', moderate: '明显', mild: '轻微', normal: '正常',
};

const SEVERITY_ICON: Record<string, React.ReactNode> = {
  severe:   <CloseCircleOutlined />,
  moderate: <ExclamationCircleOutlined />,
  mild:     <WarningOutlined />,
  normal:   <CheckCircleOutlined />,
};

// ── 工具 ──────────────────────────────────────────────────────────────────

function fmtVal(metric: string, val: number | null): string {
  if (val === null) return '—';
  if (metric === 'revenue') return `¥${val.toLocaleString('zh-CN', { maximumFractionDigits: 0 })}`;
  if (metric === 'health_score') return val.toFixed(1) + ' 分';
  return val.toFixed(1) + '%';
}

// ── 主组件 ────────────────────────────────────────────────────────────────

const FinancialAnomalyPage: React.FC = () => {
  const [storeId,      setStoreId]      = useState(localStorage.getItem('store_id') || '');
  const [storeOptions, setStoreOptions] = useState<string[]>([]);
  const [period, setPeriod] = useState(dayjs().subtract(1, 'month').format('YYYY-MM'));

  useEffect(() => {
    apiClient.get<{ items: Array<{ id: string }> }>('/api/v1/stores?limit=50')
      .then(data => {
        const ids = (data.items ?? []).map((s: { id: string }) => s.id).filter(Boolean);
        if (ids.length > 0) setStoreOptions(ids);
      })
      .catch(() => { /* 保持默认 */ });
  }, []);
  const [detectResult, setDetectResult] = useState<DetectResult | null>(null);
  const [records, setRecords] = useState<AnomalyRecord[]>([]);
  const [trend, setTrend] = useState<TrendItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [detecting, setDetecting] = useState(false);

  // 生成最近 12 个月选项
  const periodOptions = Array.from({ length: 12 }, (_, i) =>
    dayjs().subtract(i + 1, 'month').format('YYYY-MM')
  );

  const fetchRecords = async () => {
    setLoading(true);
    try {
      const [recResp, trendResp] = await Promise.all([
        apiClient.get(`/api/v1/fin-anomaly/${storeId}?only_anomalies=true&limit=100`),
        apiClient.get(`/api/v1/fin-anomaly/trend/${storeId}?periods=6`),
      ]);
      setRecords(recResp.data.records ?? []);
      setTrend(trendResp.data.trend ?? []);
    } catch (err) {
      handleApiError(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchRecords(); }, []);

  const handleDetect = async () => {
    setDetecting(true);
    try {
      const resp = await apiClient.post(
        `/api/v1/fin-anomaly/detect/${storeId}?period=${period}`
      );
      setDetectResult(resp.data);
      await fetchRecords();
      message.success(`检测完成，发现 ${resp.data.anomaly_count} 个异常`);
    } catch (err) {
      handleApiError(err);
    } finally {
      setDetecting(false);
    }
  };

  const handleResolve = async (rec: AnomalyRecord) => {
    try {
      await apiClient.post(
        `/api/v1/fin-anomaly/resolve/${storeId}?period=${rec.period}&metric=${rec.metric}`
      );
      message.success('已标记为已解决');
      await fetchRecords();
    } catch (err) {
      handleApiError(err);
    }
  };

  // ── 趋势图 ──────────────────────────────────────────────────────────────

  const trendOption = {
    tooltip: { trigger: 'axis' },
    legend: { data: ['严重', '明显', '轻微'], bottom: 0 },
    grid: { left: 40, right: 20, top: 20, bottom: 40 },
    xAxis: {
      type: 'category',
      data: trend.map((t) => t.period),
    },
    yAxis: { type: 'value', minInterval: 1 },
    series: [
      {
        name: '严重',
        type: 'bar',
        stack: 'total',
        data: trend.map((t) => t.severe),
        itemStyle: { color: SEVERITY_COLOR.severe },
      },
      {
        name: '明显',
        type: 'bar',
        stack: 'total',
        data: trend.map((t) => t.moderate),
        itemStyle: { color: SEVERITY_COLOR.moderate },
      },
      {
        name: '轻微',
        type: 'bar',
        stack: 'total',
        data: trend.map((t) => t.mild),
        itemStyle: { color: SEVERITY_COLOR.mild },
      },
    ],
  };

  // ── 当期检测结果的饼图 ───────────────────────────────────────────────────

  const pieOption = detectResult
    ? {
        tooltip: { trigger: 'item' },
        series: [
          {
            type: 'pie',
            radius: ['50%', '70%'],
            data: [
              { name: '严重', value: detectResult.severity_counts.severe,   itemStyle: { color: SEVERITY_COLOR.severe } },
              { name: '明显', value: detectResult.severity_counts.moderate, itemStyle: { color: SEVERITY_COLOR.moderate } },
              { name: '轻微', value: detectResult.severity_counts.mild,     itemStyle: { color: SEVERITY_COLOR.mild } },
              { name: '正常', value: detectResult.severity_counts.normal,   itemStyle: { color: SEVERITY_COLOR.normal } },
            ],
            label: { formatter: '{b}: {c}' },
          },
        ],
      }
    : null;

  // ── 表格列 ──────────────────────────────────────────────────────────────

  const columns = [
    {
      title: '指标',
      dataIndex: 'label',
      width: 100,
      render: (v: string) => <strong>{v}</strong>,
    },
    {
      title: '期间',
      dataIndex: 'period',
      width: 90,
    },
    {
      title: '严重度',
      dataIndex: 'severity',
      width: 90,
      render: (v: string) => (
        <Tag color={SEVERITY_COLOR[v]} icon={SEVERITY_ICON[v]}>
          {SEVERITY_LABEL[v] ?? v}
        </Tag>
      ),
    },
    {
      title: '实际值',
      key: 'actual',
      width: 110,
      render: (_: unknown, r: AnomalyRecord) => fmtVal(r.metric, r.actual_value),
    },
    {
      title: '参考值',
      key: 'expected',
      width: 110,
      render: (_: unknown, r: AnomalyRecord) => fmtVal(r.metric, r.expected_value),
    },
    {
      title: '偏差',
      dataIndex: 'deviation_pct',
      width: 90,
      render: (v: number | null) =>
        v === null ? '—' : (
          <span style={{ color: Math.abs(v) > 20 ? SEVERITY_COLOR.severe : SEVERITY_COLOR.moderate }}>
            {v > 0 ? '+' : ''}{v.toFixed(1)}%
          </span>
        ),
    },
    {
      title: '¥影响',
      dataIndex: 'yuan_impact',
      width: 110,
      render: (v: number | null) =>
        v === null ? '—' : (
          <span style={{ color: v < 0 ? SEVERITY_COLOR.severe : SEVERITY_COLOR.normal }}>
            {v > 0 ? '+' : ''}¥{Math.abs(v).toLocaleString('zh-CN', { maximumFractionDigits: 0 })}
          </span>
        ),
    },
    {
      title: '描述',
      dataIndex: 'description',
      ellipsis: true,
    },
    {
      title: '状态',
      dataIndex: 'resolved',
      width: 90,
      render: (v: boolean) =>
        v ? <Tag color="green">已解决</Tag> : <Tag color="red">待处理</Tag>,
    },
    {
      title: '操作',
      key: 'action',
      width: 90,
      render: (_: unknown, r: AnomalyRecord) =>
        !r.resolved ? (
          <Button size="small" type="link" onClick={() => handleResolve(r)}>
            标记解决
          </Button>
        ) : null,
    },
  ];

  // ── KPI 摘要卡 ──────────────────────────────────────────────────────────

  const totalAnomalies = records.length;
  const severeCount   = records.filter((r) => r.severity === 'severe').length;
  const moderateCount = records.filter((r) => r.severity === 'moderate').length;
  const mildCount     = records.filter((r) => r.severity === 'mild').length;
  const resolvedCount = records.filter((r) => r.resolved).length;
  const resolveRate   = totalAnomalies > 0 ? Math.round(resolvedCount / totalAnomalies * 100) : 100;

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <h2 className={styles.title}>财务异常检测引擎</h2>
        <div className={styles.controls}>
          <Select value={storeId} onChange={setStoreId} style={{ width: 110 }}>
            {storeOptions.map(s => <Option key={s} value={s}>{s}</Option>)}
          </Select>
          <Select
            value={period}
            onChange={setPeriod}
            style={{ width: 120 }}
          >
            {periodOptions.map((p) => (
              <Option key={p} value={p}>{p}</Option>
            )) : null}
          </Select>
          <Button
            type="primary"
            icon={<ReloadOutlined />}
            loading={detecting}
            onClick={handleDetect}
          >
            触发检测
          </Button>
        </div>
      </div>

      {/* KPI 卡 */}
      <Row gutter={[16, 16]} className={styles.kpiRow}>
        <Col xs={12} sm={6}>
          <Card className={styles.kpiCard}>
            <Statistic title="历史异常总计" value={totalAnomalies} suffix="条" />
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card className={styles.kpiCard} style={{ borderTop: `3px solid ${SEVERITY_COLOR.severe}` }}>
            <Statistic
              title="严重异常"
              value={severeCount}
              suffix="条"
              valueStyle={{ color: SEVERITY_COLOR.severe }}
            />
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card className={styles.kpiCard} style={{ borderTop: `3px solid ${SEVERITY_COLOR.moderate}` }}>
            <Statistic
              title="明显异常"
              value={moderateCount}
              suffix="条"
              valueStyle={{ color: SEVERITY_COLOR.moderate }}
            />
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card className={styles.kpiCard}>
            <Statistic title="解决率" value={resolveRate} suffix="%" />
            <Progress percent={resolveRate} size="small" showInfo={false} style={{ marginTop: 8 }} />
          </Card>
        </Col>
      </Row>

      <Tabs
        defaultActiveKey="records"
        items={[
          {
            key: 'records',
            label: '异常记录',
            children: (
              <Spin spinning={loading}>
                {records.length === 0 ? (
                  <Empty description="暂无异常记录，点击「触发检测」开始分析" />
                ) : (
                  <Table
                    dataSource={records}
                    columns={columns}
                    rowKey={(r) => `${r.period}-${r.metric}`}
                    size="small"
                    pagination={{ pageSize: 20 }}
                    rowClassName={(r) =>
                      r.severity === 'severe' ? styles.rowSevere :
                      r.severity === 'moderate' ? styles.rowModerate : ''
                    }
                  />
                )}
              </Spin>
            ),
          },
          {
            key: 'trend',
            label: '趋势分析',
            children: (
              <Row gutter={[16, 16]}>
                <Col xs={24} lg={detectResult ? 14 : 24}>
                  <Card title="近6期异常趋势（堆叠柱状）" size="small">
                    {trend.length === 0 ? (
                      <Empty description="暂无趋势数据" />
                    ) : (
                      <ReactECharts option={trendOption} style={{ height: 280 }} />
                    )}
                  </Card>
                </Col>
                {detectResult && pieOption && (
                  <Col xs={24} lg={10}>
                    <Card title={`${detectResult.period} 当期检测结果`} size="small">
                      <Row gutter={8} className={styles.detectStats}>
                        <Col span={12}>
                          <Statistic title="检测指标" value={detectResult.metrics_checked} />
                        </Col>
                        <Col span={12}>
                          <Statistic
                            title="发现异常"
                            value={detectResult.anomaly_count}
                            valueStyle={{ color: detectResult.anomaly_count > 0 ? SEVERITY_COLOR.severe : SEVERITY_COLOR.normal }}
                          />
                        </Col>
                      </Row>
                      <ReactECharts option={pieOption} style={{ height: 200 }} />
                    </Card>
                  </Col>
                )}
              </Row>
            ),
          },
          {
            key: 'detail',
            label: '检测明细',
            children: detectResult ? (
              <Row gutter={[12, 12]}>
                {detectResult.all_results.map((r) => (
                  <Col xs={24} sm={12} key={r.metric}>
                    <Card
                      size="small"
                      className={styles.detailCard}
                      style={{ borderLeft: `4px solid ${SEVERITY_COLOR[r.severity]}` }}
                    >
                      <div className={styles.detailHeader}>
                        <strong>{r.label}</strong>
                        <Tag color={SEVERITY_COLOR[r.severity]}>
                          {SEVERITY_LABEL[r.severity]}
                        </Tag>
                      </div>
                      <Row gutter={8} className={styles.detailRow}>
                        <Col span={12}>
                          <div className={styles.detailLabel}>实际值</div>
                          <div className={styles.detailValue}>{fmtVal(r.metric, r.actual_value)}</div>
                        </Col>
                        <Col span={12}>
                          <div className={styles.detailLabel}>参考值</div>
                          <div className={styles.detailValue}>{fmtVal(r.metric, r.expected_value)}</div>
                        </Col>
                      </Row>
                      <Row gutter={8}>
                        <Col span={12}>
                          <div className={styles.detailLabel}>偏差</div>
                          <div
                            className={styles.detailValue}
                            style={{ color: r.deviation_pct !== null && Math.abs(r.deviation_pct) > 10 ? SEVERITY_COLOR.moderate : undefined }}
                          >
                            {r.deviation_pct !== null ? `${r.deviation_pct > 0 ? '+' : ''}${r.deviation_pct.toFixed(1)}%` : '—'}
                          </div>
                        </Col>
                        <Col span={12}>
                          <div className={styles.detailLabel}>Z-score</div>
                          <div className={styles.detailValue}>
                            {r.z_score !== null ? r.z_score.toFixed(2) : '—'}
                          </div>
                        </Col>
                      </Row>
                      {r.description && (
                        <div className={styles.detailDesc}>{r.description}</div>
                      )}
                    </Card>
                  </Col>
                ))}
              </Row>
            ) : (
              <Empty description="请先选择期间并点击「触发检测」" />
            ),
          },
        ]}
      />
    </div>
  );
};

export default FinancialAnomalyPage;
