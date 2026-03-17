/**
 * 经营作战台（DailyHub）— 重构版
 * 布局：KPI 条 → 运营节奏轴（左）+ 异常/机会双列（中右）→ 备战板（底部）
 */
import React, { useState, useCallback, useEffect } from 'react';
import {
  Row, Col, Card, Select, Button, Alert, Tag, Table, Statistic,
  Space, Spin, Typography, Divider, Badge,
  List, Tooltip, message,
} from 'antd';
import {
  CheckCircleOutlined, ReloadOutlined, WarningOutlined,
  RiseOutlined, FallOutlined, ThunderboltOutlined,
  ClockCircleOutlined, FireOutlined, BulbOutlined,
  DollarOutlined, TeamOutlined, HeartOutlined,
} from '@ant-design/icons';
import ReactECharts from 'echarts-for-react';
import { apiClient } from '../services/api';
import { useAuth } from '../contexts/AuthContext';
import AISuggestionCard from '../design-system/components/AISuggestionCard';
import { OpsTimeline } from '../design-system/components';

const { Option } = Select;
const { Text, Title } = Typography;

// ── 运营节奏时间轴 ────────────────────────────────────────────────────────────

const OPS_PHASES = [
  { label: '班前准备',   start:  0, end: 10.5, icon: <TeamOutlined />,         color: '#8c8c8c' },
  { label: '午市中',     start: 10.5, end: 14,  icon: <FireOutlined />,         color: '#C8923A' },
  { label: '午市收尾',  start: 14,  end: 16,  icon: <ClockCircleOutlined />,   color: '#0AAF9A' },
  { label: '晚市备战',  start: 16,  end: 17.5, icon: <BulbOutlined />,         color: '#722ed1' },
  { label: '晚市中',     start: 17.5, end: 21,  icon: <FireOutlined />,         color: '#C53030' },
  { label: '日结复盘',  start: 21,  end: 24,  icon: <CheckCircleOutlined />,   color: '#1A7A52' },
];

function currentPhaseIndex(): number {
  const h = new Date().getHours() + new Date().getMinutes() / 60;
  return OPS_PHASES.findIndex(p => h >= p.start && h < p.end) ?? 0;
}

// ── 工具 ─────────────────────────────────────────────────────────────────────

const yuanFmt = (v?: number | null, fallback = '—') =>
  v == null ? fallback : `¥${v.toFixed(0)}`;

// ── KPI 数据来源 ──────────────────────────────────────────────────────────────

async function loadKpiData(storeId: string) {
  const [bffRes, energyRes, anomalyRes] = await Promise.allSettled([
    apiClient.get(`/api/v1/bff/sm/${storeId}`),
    apiClient.get(`/api/v1/energy/stores/${storeId}/dashboard`, { params: { brand_id: 'brand_001' } }),
    apiClient.get(`/api/v1/energy/stores/${storeId}/anomalies`, { params: { limit: 20 } }),
  ]);

  const bff     = bffRes.status     === 'fulfilled' ? bffRes.value     : null;
  const energy  = energyRes.status  === 'fulfilled' ? energyRes.value  : null;
  const anomalies = anomalyRes.status === 'fulfilled' ? anomalyRes.value : [];

  return { bff, energy, anomalies };
}

// ═══════════════════════════════════════════════════════════════════════════
// 主组件
// ═══════════════════════════════════════════════════════════════════════════

const DailyHubPage: React.FC = () => {
  const { user } = useAuth();
  const [loading, setLoading]   = useState(false);
  const [approving, setApproving] = useState(false);
  const [selectedStore, setSelectedStore] = useState(user?.store_id || 'STORE001');
  const [board, setBoard]       = useState<any>(null);
  const [kpi, setKpi]           = useState<any>(null);
  const phaseIdx = currentPhaseIndex();

  const loadAll = useCallback(async () => {
    setLoading(true);
    try {
      const [boardRes, kpiData] = await Promise.allSettled([
        apiClient.get(`/api/v1/daily-hub/${selectedStore}`),
        loadKpiData(selectedStore),
      ]);
      if (boardRes.status === 'fulfilled') setBoard(boardRes.value);
      if (kpiData.status === 'fulfilled')  setKpi(kpiData.value);
      const failCount = [boardRes, kpiData].filter(r => r.status === 'rejected').length;
      if (failCount > 0) message.warning('部分数据加载失败，已显示缓存');
    } finally {
      setLoading(false);
    }
  }, [selectedStore]);

  useEffect(() => { loadAll(); }, [loadAll]);

  const handleApprove = async () => {
    if (!board) return;
    setApproving(true);
    try {
      const res = await apiClient.post(`/api/v1/daily-hub/${selectedStore}/approve`, {
        target_date: board.target_date,
      });
      setBoard(res.data);
    } finally {
      setApproving(false);
    }
  };

  // 聚合数据
  const bff       = kpi?.bff;
  const energy    = kpi?.energy;
  const anomalies: any[] = kpi?.anomalies ?? [];
  const decisions: any[] = bff?.top3_decisions ?? [];
  const forecast  = board?.tomorrow_forecast;
  const banquet   = forecast?.banquet_track;
  const review    = board?.yesterday_review;
  const isApproved = board?.approval_status === 'approved' || board?.approval_status === 'adjusted';

  // 健康评分相关
  const healthScore = bff?.health_score?.overall ?? null;
  const healthColor = healthScore == null ? '#d9d9d9'
    : healthScore >= 80 ? '#1A7A52'
    : healthScore >= 60 ? '#faad14' : '#C53030';

  // 能耗数据
  const todayKwh  = energy?.today?.kwh;
  const todayCost = energy?.today?.cost_yuan;
  const anomalyCount = anomalies.length;

  // 图表
  const barChartOption = {
    title: { text: '明日营收构成', left: 'center', textStyle: { fontSize: 12 } },
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'category', data: ['宴会', '散客'] },
    yAxis: { type: 'value', name: '元', axisLabel: { fontSize: 11 } },
    series: [{
      type: 'bar',
      data: [
        { value: ((banquet?.deterministic_revenue || 0) / 100).toFixed(0), itemStyle: { color: '#f5a623' } },
        { value: ((forecast?.regular_track?.predicted_revenue || 0) / 100).toFixed(0), itemStyle: { color: '#0AAF9A' } },
      ],
    }],
  };

  return (
    <div>
      {/* ── 顶部工具栏 ─────────────────────────────────────────────────── */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <Space>
          <Select value={selectedStore} onChange={setSelectedStore} style={{ width: 160 }}>
            <Option value="STORE001">STORE001</Option>
          </Select>
          <Button icon={<ReloadOutlined />} onClick={loadAll} loading={loading}>刷新</Button>
        </Space>
        <Space>
          {board && (
            <Tag color={isApproved ? 'green' : 'orange'}>
              {isApproved ? '✓ 已确认备战' : '待确认备战'}
            </Tag>
          )}
          <Tag color="blue">
            <ClockCircleOutlined /> {OPS_PHASES[phaseIdx]?.label ?? '——'}
          </Tag>
        </Space>
      </div>

      <Spin spinning={loading}>
        {/* ══════════════════════════════════════════════════════════════════
            KPI 条（6 格）
        ══════════════════════════════════════════════════════════════════ */}
        <Row gutter={[12, 12]} style={{ marginBottom: 16 }}>
          {[
            {
              title: '今日营收',
              value: review?.total_revenue ? `¥${(review.total_revenue / 100).toFixed(0)}` : '—',
              icon: <DollarOutlined style={{ color: '#0AAF9A' }} />,
              sub: review?.order_count ? `${review.order_count} 单` : null,
            },
            {
              title: '门店健康分',
              value: healthScore != null ? healthScore : '—',
              icon: <HeartOutlined style={{ color: healthColor }} />,
              sub: healthScore != null ? (healthScore >= 80 ? '优秀' : healthScore >= 60 ? '一般' : '需关注') : null,
              color: healthColor,
            },
            {
              title: '今日用电',
              value: todayKwh ? `${todayKwh.toFixed(1)} 度` : '—',
              icon: <ThunderboltOutlined style={{ color: '#faad14' }} />,
              sub: todayCost ? `¥${todayCost.toFixed(0)}` : null,
            },
            {
              title: '未处理异常',
              value: anomalyCount,
              icon: <WarningOutlined style={{ color: anomalyCount > 0 ? '#C53030' : '#1A7A52' }} />,
              sub: anomalyCount > 0 ? '需处理' : '一切正常',
              color: anomalyCount > 0 ? '#C53030' : '#1A7A52',
            },
            {
              title: 'AI 建议数',
              value: decisions.length,
              icon: <BulbOutlined style={{ color: '#722ed1' }} />,
              sub: decisions[0] ? `¥${decisions[0].expected_saving_yuan?.toFixed(0)} 可节省` : null,
            },
            {
              title: '预测明日营收',
              value: forecast?.total_predicted_revenue
                ? `¥${(forecast.total_predicted_revenue / 100).toFixed(0)}`
                : '—',
              icon: <RiseOutlined style={{ color: '#1A7A52' }} />,
              sub: banquet?.active ? '宴会熔断' : null,
            },
          ].map((item, i) => (
            <Col key={i} xs={12} sm={8} md={4}>
              <Card size="small" bodyStyle={{ padding: '10px 14px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
                  {item.icon}
                  <Text style={{ fontSize: 12, color: '#888' }}>{item.title}</Text>
                </div>
                <div style={{ fontSize: 20, fontWeight: 700, color: item.color ?? '#262626', lineHeight: 1.2 }}>
                  {item.value}
                </div>
                {item.sub && (
                  <Text style={{ fontSize: 11, color: '#aaa' }}>{item.sub}</Text>
                )}
              </Card>
            </Col>
          ))}
        </Row>

        {/* ══════════════════════════════════════════════════════════════════
            中间行：运营节奏 | 异常事件 | 经营机会
        ══════════════════════════════════════════════════════════════════ */}
        <Row gutter={[12, 12]} style={{ marginBottom: 16 }}>
          {/* 左：今日运营节奏 */}
          <Col xs={24} md={6}>
            <Card title="今日运营节奏" size="small" style={{ height: '100%' }}>
              <OpsTimeline phases={OPS_PHASES} currentIndex={phaseIdx} />
            </Card>
          </Col>

          {/* 中：异常事件 */}
          <Col xs={24} md={9}>
            <Card
              title={
                <Space>
                  <WarningOutlined style={{ color: '#C53030' }} />
                  <span>异常事件</span>
                  {anomalyCount > 0 && <Badge count={anomalyCount} style={{ backgroundColor: '#C53030' }} />}
                </Space>
              }
              size="small"
              style={{ height: '100%' }}
              extra={<a href="/energy" style={{ fontSize: 12 }}>全部 →</a>}
            >
              {anomalies.length === 0 ? (
                <div style={{ textAlign: 'center', padding: '24px 0', color: '#1A7A52' }}>
                  <CheckCircleOutlined style={{ fontSize: 24 }} />
                  <div style={{ marginTop: 8, fontSize: 13 }}>暂无异常，经营正常</div>
                </div>
              ) : (
                <List
                  size="small"
                  dataSource={anomalies.slice(0, 5)}
                  renderItem={(item: any) => (
                    <List.Item style={{ padding: '6px 0' }}>
                      <List.Item.Meta
                        avatar={
                          <Tag
                            color={item.severity === 'high' ? 'error' : item.severity === 'medium' ? 'warning' : 'default'}
                            style={{ fontSize: 10, margin: 0 }}
                          >
                            {item.severity === 'high' ? '高危' : item.severity === 'medium' ? '中危' : '低危'}
                          </Tag>
                        }
                        title={<Text style={{ fontSize: 12 }}>{item.title}</Text>}
                        description={
                          <Text style={{ fontSize: 11, color: '#888' }}>
                            {item.action_hint?.slice(0, 40)}{item.action_hint?.length > 40 ? '…' : ''}
                          </Text>
                        }
                      />
                    </List.Item>
                  )}
                />
              )}
              {anomalies.length > 5 && (
                <Text type="secondary" style={{ fontSize: 11 }}>
                  还有 {anomalies.length - 5} 条未显示 →
                </Text>
              )}
            </Card>
          </Col>

          {/* 右：经营机会（来自 Top3 决策） */}
          <Col xs={24} md={9}>
            <Card
              title={
                <Space>
                  <BulbOutlined style={{ color: '#faad14' }} />
                  <span>经营机会</span>
                  {decisions.length > 0 && <Badge count={decisions.length} style={{ backgroundColor: '#faad14' }} />}
                </Space>
              }
              size="small"
              style={{ height: '100%' }}
              extra={<a href="/daily-hub" style={{ fontSize: 12 }}>AI助手 →</a>}
            >
              {decisions.length === 0 ? (
                <div style={{ textAlign: 'center', padding: '24px 0', color: '#aaa' }}>
                  <BulbOutlined style={{ fontSize: 24 }} />
                  <div style={{ marginTop: 8, fontSize: 13 }}>暂无建议</div>
                </div>
              ) : (
                decisions.slice(0, 3).map((item: any) => (
                  <AISuggestionCard
                    key={item.rank ?? item.title}
                    rank={item.rank}
                    title={item.title}
                    action={item.action}
                    savingYuan={item.expected_saving_yuan}
                    confidencePct={item.confidence_pct}
                    difficulty={item.execution_difficulty}
                    windowLabel={item.decision_window_label}
                    source={item.source}
                  />
                ))
              )}
            </Card>
          </Col>
        </Row>

        {/* ══════════════════════════════════════════════════════════════════
            底部：昨日复盘 | 明日预测 | 行动面板（原有）
        ══════════════════════════════════════════════════════════════════ */}
        <Divider style={{ margin: '4px 0 12px' }}>备战板</Divider>
        <Row gutter={16}>
          {/* 昨日复盘 */}
          <Col xs={24} md={8}>
            <Card title="昨日复盘" size="small" style={{ marginBottom: 16 }}>
              <Row gutter={8}>
                <Col span={12}>
                  <Statistic title="总营收" value={(review?.total_revenue || 0) / 100} prefix="¥" precision={0} />
                </Col>
                <Col span={12}>
                  <Statistic title="订单数" value={review?.order_count || 0} />
                </Col>
              </Row>
              {(review?.highlights || []).map((h: string, i: number) => (
                <div key={i} style={{ fontSize: 12, marginTop: 4 }}>✓ {h}</div>
              ))}
              {(review?.alerts || []).map((a: string, i: number) => (
                <div key={i} style={{ fontSize: 12, color: '#C8923A', marginTop: 4 }}>⚠ {a}</div>
              ))}
            </Card>
          </Col>

          {/* 明日预测 */}
          <Col xs={24} md={8}>
            <Card title="明日预测" size="small" style={{ marginBottom: 16 }}>
              {banquet?.active && (
                <Alert
                  message={`宴会熔断：${banquet.banquets?.length ?? 0} 场，确定营收 ¥${((banquet.deterministic_revenue || 0) / 100).toFixed(0)}`}
                  type="warning" showIcon style={{ marginBottom: 8 }}
                />
              )}
              <Row gutter={8} style={{ marginBottom: 8 }}>
                <Col span={12}>
                  <Statistic
                    title="预测总营收"
                    value={(forecast?.total_predicted_revenue || 0) / 100}
                    prefix="¥" precision={0}
                  />
                </Col>
                <Col span={12}>
                  <div style={{ fontSize: 11, color: '#888', marginTop: 4 }}>
                    置信区间<br />
                    ¥{((forecast?.total_lower || 0) / 100).toFixed(0)} ~ ¥{((forecast?.total_upper || 0) / 100).toFixed(0)}
                  </div>
                </Col>
              </Row>
              <ReactECharts option={barChartOption} style={{ height: 160 }} />
            </Card>
          </Col>

          {/* 行动面板 */}
          <Col xs={24} md={8}>
            <Card title="行动面板" size="small" style={{ marginBottom: 16 }}>
              <Text strong style={{ fontSize: 13 }}>采购清单</Text>
              <Table
                dataSource={board?.purchase_order || []}
                rowKey={(r: any) => r.item_name}
                size="small" pagination={false} scroll={{ y: 130 }} style={{ marginTop: 4 }}
                columns={[
                  { title: '物料', dataIndex: 'item_name' },
                  { title: '建议量', dataIndex: 'recommended_quantity', width: 65 },
                  {
                    title: '级别', dataIndex: 'alert_level', width: 60,
                    render: (v: string) => (
                      <Tag color={v === 'critical' ? 'red' : v === 'urgent' ? 'orange' : 'gold'} style={{ fontSize: 10 }}>
                        {v}
                      </Tag>
                    ),
                  },
                ]}
              />
              <Divider style={{ margin: '8px 0' }} />
              <Text strong style={{ fontSize: 13 }}>
                排班（{board?.staffing_plan?.total_staff || 0} 人）
              </Text>
              <Table
                dataSource={board?.staffing_plan?.shifts || []}
                rowKey={(_: any, i: any) => i}
                size="small" pagination={false} scroll={{ y: 100 }} style={{ marginTop: 4 }}
                columns={[
                  { title: '员工', dataIndex: 'employee_id', width: 70 },
                  { title: '班次', dataIndex: 'shift_type' },
                  { title: '时间', dataIndex: 'start_time', width: 50 },
                ]}
              />
              <Button
                type="primary" icon={<CheckCircleOutlined />} block
                style={{ marginTop: 12 }}
                loading={approving} disabled={isApproved}
                onClick={handleApprove}
              >
                {isApproved ? '已确认备战' : '一键确认备战'}
              </Button>
            </Card>
          </Col>
        </Row>
      </Spin>
    </div>
  );
};

export default DailyHubPage;
