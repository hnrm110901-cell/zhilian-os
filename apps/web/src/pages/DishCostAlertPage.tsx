/**
 * 菜品成本预警引擎 — Phase 6 Month 3
 * 监控食材成本率/毛利率/BCG象限环比变化，自动告警并量化¥损失
 */
import React, { useState, useEffect, useCallback } from 'react';
import {
  Row, Col, Card, Statistic, Select, Button, Table, Tag, Tabs, Spin,
  Typography, Space, Tooltip, message, Empty, Badge, Popconfirm, Alert,
} from 'antd';
import {
  WarningOutlined, FireOutlined, DollarOutlined, CheckCircleOutlined,
  SyncOutlined, LineChartOutlined, BarChartOutlined, BellOutlined,
} from '@ant-design/icons';
import ReactECharts from 'echarts-for-react';
import dayjs from 'dayjs';
import { apiClient, handleApiError } from '../services/api';
import styles from './DishCostAlertPage.module.css';

const { Title, Text } = Typography;
const { Option } = Select;

// ── 配置 ──────────────────────────────────────────────────────────────────────
const SEVERITY_CONFIG: Record<string, { label: string; color: string; antColor: string }> = {
  critical: { label: '严重', color: '#C53030', antColor: 'red' },
  warning:  { label: '警告', color: '#C8923A', antColor: 'orange' },
  info:     { label: '提示', color: '#0AAF9A', antColor: 'blue' },
};

const ALERT_TYPE_CONFIG: Record<string, { label: string; color: string; icon: string }> = {
  fcr_spike:     { label: '成本率飙升', color: '#C53030', icon: '📈' },
  margin_drop:   { label: '毛利率下滑', color: '#C8923A', icon: '📉' },
  bcg_downgrade: { label: 'BCG象限下降', color: '#722ed1', icon: '⬇️' },
};

// ── 类型 ──────────────────────────────────────────────────────────────────────
interface DishAlert {
  id: number;
  dish_id: string;
  dish_name: string;
  category: string;
  bcg_quadrant: string;
  prev_bcg_quadrant: string;
  alert_type: string;
  alert_label: string;
  severity: string;
  current_value: number;
  prev_value: number;
  change_pp: number;
  yuan_impact_yuan: number;
  message: string;
  status: string;
  computed_at: string | null;
}

interface AlertSummary {
  by_type: Array<{
    alert_type: string;
    label: string;
    count: number;
    total_impact: number;
    open: number;
    resolved: number;
  }>;
  by_severity: { critical: number; warning: number; info: number };
  total_open_yuan_impact: number;
  open_count: number;
  resolved_count: number;
  critical_count: number;
}

interface TrendPoint {
  period: string;
  dish_count: number;
  avg_fcr: number;
  avg_gpm: number;
  total_revenue: number;
  total_profit: number;
  total_orders: number;
}

// ── 辅助 ──────────────────────────────────────────────────────────────────────
const fmt = (n: number) =>
  `¥${Math.abs(n).toFixed(0).replace(/\B(?=(\d{3})+(?!\d))/g, ',')}`;
const fmtPct = (n: number) => `${n.toFixed(1)}%`;
const fmtPP  = (n: number) => `${n > 0 ? '+' : ''}${n.toFixed(1)}pp`;

// ── 主页面 ────────────────────────────────────────────────────────────────────
const DishCostAlertPage: React.FC = () => {
  const [storeId,      setStoreId]      = useState('S001');
  const [storeOptions, setStoreOptions] = useState<string[]>(['S001']);
  const [period,       setPeriod]       = useState(dayjs().subtract(1, 'month').format('YYYY-MM'));

  useEffect(() => {
    apiClient.get<{ items: Array<{ id: string }> }>('/api/v1/stores?limit=50')
      .then(data => {
        const ids = (data.items ?? []).map((s: { id: string }) => s.id).filter(Boolean);
        if (ids.length > 0) setStoreOptions(ids);
      })
      .catch(() => { /* 保持默认 */ });
  }, []);
  const [detecting,  setDetecting]  = useState(false);
  const [loading,    setLoading]    = useState(false);
  const [resolving,  setResolving]  = useState(false);
  const [alerts,     setAlerts]     = useState<DishAlert[]>([]);
  const [summary,    setSummary]    = useState<AlertSummary | null>(null);
  const [trend,      setTrend]      = useState<TrendPoint[]>([]);
  const [sevFilter,  setSevFilter]  = useState<string | undefined>(undefined);
  const [statFilter, setStatFilter] = useState<string>('open');
  const [activeTab,  setActiveTab]  = useState('list');

  const fetchAll = useCallback(async () => {
    setLoading(true);
    try {
      const [alertRes, sumRes, trendRes] = await Promise.all([
        apiClient.get(`/api/v1/dish-alert/${storeId}`, {
          params: { period, severity: sevFilter, status: statFilter, limit: 100 },
        }),
        apiClient.get(`/api/v1/dish-alert/summary/${storeId}`, { params: { period } }),
        apiClient.get(`/api/v1/dish-alert/trend/${storeId}`, { params: { period, periods: 6 } }),
      ]);
      setAlerts(alertRes.data.alerts    || []);
      setSummary(sumRes.data            || null);
      setTrend(trendRes.data.trend      || []);
    } catch (e) {
      handleApiError(e);
    } finally {
      setLoading(false);
    }
  }, [storeId, period, sevFilter, statFilter]);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  const handleDetect = async () => {
    setDetecting(true);
    try {
      const res = await apiClient.post(`/api/v1/dish-alert/detect/${storeId}`,
        null, { params: { period } });
      message.success(
        `检测完成：${res.data.dish_count} 道菜，生成 ${res.data.alert_count} 条预警`
      );
      fetchAll();
    } catch (e) { handleApiError(e); }
    finally { setDetecting(false); }
  };

  const handleResolve = async (alertId: number) => {
    setResolving(true);
    try {
      await apiClient.post(`/api/v1/dish-alert/${alertId}/resolve`);
      message.success('已标记为已解决');
      fetchAll();
    } catch (e) { handleApiError(e); }
    finally { setResolving(false); }
  };

  // ── KPI ───────────────────────────────────────────────────────────────────
  const openCount    = summary?.open_count    ?? 0;
  const critCount    = summary?.critical_count ?? 0;
  const totalImpact  = summary?.total_open_yuan_impact ?? 0;
  const resolvedCount= summary?.resolved_count ?? 0;

  // ── 趋势图 ────────────────────────────────────────────────────────────────
  const trendOption = () => ({
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis' },
    legend: { data: ['平均食材成本率%', '平均毛利率%'], bottom: 0 },
    grid: { left: 55, right: 20, top: 40, bottom: 50 },
    xAxis: { type: 'category', data: trend.map(t => t.period) },
    yAxis: { type: 'value', min: 0, max: 100, axisLabel: { formatter: '{value}%' } },
    series: [
      {
        name: '平均食材成本率%', type: 'line', smooth: true,
        data: trend.map(t => t.avg_fcr.toFixed(1)),
        itemStyle: { color: '#C53030' },
        areaStyle: { color: 'rgba(255,77,79,0.1)' },
        markLine: { data: [{ type: 'average', name: '均值' }] },
      },
      {
        name: '平均毛利率%', type: 'line', smooth: true,
        data: trend.map(t => t.avg_gpm.toFixed(1)),
        itemStyle: { color: '#1A7A52' },
        areaStyle: { color: 'rgba(82,196,26,0.1)' },
      },
    ],
  });

  // ── 告警类型柱图 ─────────────────────────────────────────────────────────
  const summaryBarOption = () => {
    if (!summary) return {};
    const types = summary.by_type.filter(t => t.count > 0);
    return {
      backgroundColor: 'transparent',
      tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
      legend: { data: ['待处理', '已解决'], bottom: 0 },
      grid: { left: 50, right: 20, top: 30, bottom: 50 },
      xAxis: { type: 'category', data: types.map(t => t.label) },
      yAxis: { type: 'value', name: '条数' },
      series: [
        {
          name: '待处理', type: 'bar',
          data: types.map(t => ({
            value: t.open,
            itemStyle: { color: ALERT_TYPE_CONFIG[t.alert_type]?.color || '#aaa' },
          })),
          stack: 'total',
          label: { show: true, position: 'inside' },
        },
        {
          name: '已解决', type: 'bar',
          data: types.map(t => t.resolved),
          stack: 'total',
          itemStyle: { color: '#bbb' },
        },
      ],
    };
  };

  // ── 告警严重度饼图 ────────────────────────────────────────────────────────
  const severityPieOption = () => {
    if (!summary) return {};
    return {
      backgroundColor: 'transparent',
      tooltip: { trigger: 'item', formatter: '{b}: {c}条 ({d}%)' },
      series: [{
        type: 'pie', radius: ['40%', '70%'],
        data: [
          { name: '严重', value: summary.by_severity.critical, itemStyle: { color: '#C53030' } },
          { name: '警告', value: summary.by_severity.warning,  itemStyle: { color: '#C8923A' } },
          { name: '提示', value: summary.by_severity.info,     itemStyle: { color: '#0AAF9A' } },
        ].filter(d => d.value > 0),
        label: { formatter: '{b}\n{c}条' },
      }],
    };
  };

  // ── 告警列表列 ────────────────────────────────────────────────────────────
  const columns = [
    {
      title: '严重度', dataIndex: 'severity', width: 80,
      render: (s: string) => {
        const cfg = SEVERITY_CONFIG[s] || { label: s, antColor: 'default' };
        return <Tag color={cfg.antColor}>{cfg.label}</Tag>;
      },
      sorter: (a: DishAlert, b: DishAlert) => {
        const order = { critical: 3, warning: 2, info: 1 };
        return (order[b.severity as keyof typeof order] || 0) -
               (order[a.severity as keyof typeof order] || 0);
      },
    },
    {
      title: '菜品', dataIndex: 'dish_name', width: 120,
      render: (n: string, r: DishAlert) => (
        <Space direction="vertical" size={2}>
          <Text strong>{n}</Text>
          <Text type="secondary" style={{ fontSize: 11 }}>{r.category}</Text>
        </Space>
      ),
    },
    {
      title: '告警类型', dataIndex: 'alert_type', width: 130,
      render: (t: string, r: DishAlert) => {
        const cfg = ALERT_TYPE_CONFIG[t] || { label: t, color: '#aaa', icon: '⚠️' };
        return (
          <Space>
            <span>{cfg.icon}</span>
            <Tag color={cfg.color}>{cfg.label}</Tag>
          </Space>
        );
      },
    },
    {
      title: '当期值', dataIndex: 'current_value', width: 80,
      render: (v: number, r: DishAlert) =>
        r.alert_type === 'bcg_downgrade'
          ? `象限${v.toFixed(0)}`
          : fmtPct(v),
    },
    {
      title: '上期值', dataIndex: 'prev_value', width: 80,
      render: (v: number, r: DishAlert) =>
        r.alert_type === 'bcg_downgrade'
          ? `象限${v.toFixed(0)}`
          : fmtPct(v),
    },
    {
      title: '变化', dataIndex: 'change_pp', width: 80,
      render: (v: number, r: DishAlert) => (
        <Text style={{ color: '#C53030' }}>
          {r.alert_type === 'bcg_downgrade' ? `↓${v.toFixed(0)}级` : fmtPP(v)}
        </Text>
      ),
    },
    {
      title: '¥影响', dataIndex: 'yuan_impact_yuan', width: 90,
      sorter: (a: DishAlert, b: DishAlert) => b.yuan_impact_yuan - a.yuan_impact_yuan,
      render: (v: number) => <Text style={{ color: '#C53030' }}>{fmt(v)}</Text>,
    },
    {
      title: '说明', dataIndex: 'message', ellipsis: true,
    },
    {
      title: '操作', width: 80,
      render: (_: any, r: DishAlert) =>
        r.status === 'open' ? (
          <Popconfirm title="确认标记为已解决？" onConfirm={() => handleResolve(r.id)}
            okText="确认" cancelText="取消">
            <Button size="small" type="link" loading={resolving}>解决</Button>
          </Popconfirm>
        ) : (
          <Tag color="default" style={{ margin: 0 }}>已解决</Tag>
        ),
    },
  ];

  // ── 月份选项 ──────────────────────────────────────────────────────────────
  const periodOptions = Array.from({ length: 12 }, (_, i) =>
    dayjs().subtract(i + 1, 'month').format('YYYY-MM')
  );

  return (
    <div className={styles.page}>
      {/* ── 顶部控制 ─────────────────────────────────────────────────────── */}
      <div className={styles.header}>
        <Title level={4} style={{ margin: 0 }}>
          <BellOutlined /> 菜品成本预警
        </Title>
        <Space>
          <Select value={storeId} onChange={setStoreId} style={{ width: 120 }}>
            {storeOptions.map(s => <Option key={s} value={s}>{s}</Option>)}
          </Select>
          <Select value={period} onChange={setPeriod} style={{ width: 120 }}>
            {periodOptions.map(p => <Option key={p} value={p}>{p}</Option>)}
          </Select>
          <Tooltip title="比对当期与上期BCG数据，检测成本异动">
            <Button type="primary" icon={<SyncOutlined spin={detecting} />}
              onClick={handleDetect} loading={detecting}>
              检测预警
            </Button>
          </Tooltip>
        </Space>
      </div>

      {/* ── 严重告警横幅 ─────────────────────────────────────────────────── */}
      {critCount > 0 && (
        <Alert
          type="error"
          showIcon
          icon={<FireOutlined />}
          message={`本期存在 ${critCount} 条严重预警，累计¥损失估算 ${fmt(totalImpact)}，请立即处理！`}
          style={{ borderRadius: 8 }}
        />
      )}

      {/* ── KPI 卡片 ─────────────────────────────────────────────────────── */}
      <Row gutter={[16, 16]}>
        <Col xs={12} sm={6}>
          <Card size="small">
            <Statistic title="待处理预警" value={openCount} suffix="条"
              prefix={<WarningOutlined />} valueStyle={{ color: '#C8923A' }} />
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card size="small">
            <Statistic title="严重预警" value={critCount} suffix="条"
              prefix={<FireOutlined />} valueStyle={{ color: '#C53030' }} />
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card size="small">
            <Statistic title="¥影响估算" value={totalImpact.toFixed(0)}
              prefix="¥" valueStyle={{ color: '#C53030' }} />
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card size="small">
            <Statistic title="已解决预警" value={resolvedCount} suffix="条"
              prefix={<CheckCircleOutlined />} valueStyle={{ color: '#1A7A52' }} />
          </Card>
        </Col>
      </Row>

      {/* ── 主内容 ───────────────────────────────────────────────────────── */}
      <Card bodyStyle={{ padding: '0 16px 16px' }}>
        <Tabs activeKey={activeTab} onChange={setActiveTab} items={[
          {
            key: 'list',
            label: <span><WarningOutlined /> 预警列表</span>,
            children: (
              <Spin spinning={loading}>
                <Space style={{ marginBottom: 12 }}>
                  <Select value={sevFilter} onChange={setSevFilter}
                    style={{ width: 110 }} allowClear placeholder="严重度">
                    <Option value="critical">🔴 严重</Option>
                    <Option value="warning">🟠 警告</Option>
                    <Option value="info">🔵 提示</Option>
                  </Select>
                  <Select value={statFilter} onChange={setStatFilter} style={{ width: 110 }}>
                    <Option value="open">待处理</Option>
                    <Option value="resolved">已解决</Option>
                  </Select>
                </Space>
                {alerts.length === 0 ? (
                  <Empty description="暂无预警，请先点击「检测预警」" />
                ) : (
                  <Table
                    dataSource={alerts}
                    columns={columns}
                    rowKey="id"
                    size="small"
                    pagination={{ pageSize: 20, showSizeChanger: true }}
                    scroll={{ x: 900 }}
                    rowClassName={(r) =>
                      r.severity === 'critical' ? styles.rowCritical :
                      r.severity === 'warning'  ? styles.rowWarning  : ''
                    }
                  />
                )}
              </Spin>
            ),
          },
          {
            key: 'trend',
            label: <span><LineChartOutlined /> 成本趋势</span>,
            children: (
              <Spin spinning={loading}>
                {trend.length === 0 ? (
                  <Empty description="暂无趋势数据" />
                ) : (
                  <Row gutter={16}>
                    <Col xs={24} lg={16}>
                      <Text strong style={{ display: 'block', marginBottom: 8 }}>
                        近6期门店平均食材成本率 vs 毛利率
                      </Text>
                      <ReactECharts option={trendOption()} style={{ height: 320 }} notMerge />
                    </Col>
                    <Col xs={24} lg={8}>
                      <Text strong style={{ display: 'block', marginBottom: 8 }}>
                        当期预警严重度分布
                      </Text>
                      <ReactECharts option={severityPieOption()} style={{ height: 200 }} notMerge />
                      <div className={styles.trendStats}>
                        {trend.slice(-1).map(t => (
                          <div key={t.period} className={styles.trendStatItem}>
                            <Text type="secondary">本期（{t.period}）</Text>
                            <Space>
                              <Text>菜品数: {t.dish_count}</Text>
                              <Text>总销量: {t.total_orders}</Text>
                            </Space>
                            <Space>
                              <Text style={{ color: '#C53030' }}>
                                食材成本率: {fmtPct(t.avg_fcr)}
                              </Text>
                              <Text style={{ color: '#1A7A52' }}>
                                毛利率: {fmtPct(t.avg_gpm)}
                              </Text>
                            </Space>
                          </div>
                        ))}
                      </div>
                    </Col>
                  </Row>
                )}
              </Spin>
            ),
          },
          {
            key: 'analysis',
            label: <span><BarChartOutlined /> 汇总分析</span>,
            children: (
              <Spin spinning={loading}>
                {!summary ? <Empty /> : (
                  <Row gutter={16}>
                    <Col xs={24} lg={14}>
                      <Text strong style={{ display: 'block', marginBottom: 8 }}>
                        各告警类型：待处理 vs 已解决
                      </Text>
                      <ReactECharts option={summaryBarOption()} style={{ height: 280 }} notMerge />
                    </Col>
                    <Col xs={24} lg={10}>
                      <Text strong style={{ display: 'block', marginBottom: 8 }}>
                        告警类型¥影响明细
                      </Text>
                      <Table
                        dataSource={summary.by_type}
                        rowKey="alert_type"
                        size="small"
                        pagination={false}
                        columns={[
                          {
                            title: '类型', dataIndex: 'label',
                            render: (l: string, r: any) => (
                              <Space>
                                <span>{ALERT_TYPE_CONFIG[r.alert_type]?.icon}</span>
                                <Text>{l}</Text>
                              </Space>
                            ),
                          },
                          { title: '待处理', dataIndex: 'open', width: 65 },
                          {
                            title: '¥影响', dataIndex: 'total_impact',
                            render: (v: number) => (
                              <Text style={{ color: v > 0 ? '#C53030' : '#aaa' }}>
                                {fmt(v)}
                              </Text>
                            ),
                          },
                        ]}
                      />
                    </Col>
                  </Row>
                )}
              </Spin>
            ),
          },
        ]} />
      </Card>
    </div>
  );
};

export default DishCostAlertPage;
