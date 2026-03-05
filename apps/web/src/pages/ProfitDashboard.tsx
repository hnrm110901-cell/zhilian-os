import React, { useState, useEffect, useCallback } from 'react';
import {
  Card, Row, Col, Statistic, Select, DatePicker, Space, Table,
  Tag, Typography, Spin, Alert, Button, Tabs, Progress,
} from 'antd';
import {
  ReloadOutlined, RiseOutlined, FallOutlined,
  DollarOutlined, WarningOutlined, CheckCircleOutlined,
  SearchOutlined,
} from '@ant-design/icons';
import dayjs, { Dayjs } from 'dayjs';
import ReactECharts from 'echarts-for-react';
import { apiClient } from '../services/api';
import { handleApiError } from '../utils/message';

const { Title, Text } = Typography;
const { Option } = Select;

// ── 类型定义 ──────────────────────────────────────────────────────────────────

interface StoreRankingItem {
  store_id:          string;
  store_name:        string;
  actual_cost_pct:   number;
  theoretical_pct:   number;
  variance_pct:      number;
  variance_status:   'ok' | 'warning' | 'critical';
  actual_cost_yuan:  number;
  revenue_yuan:      number;
  top_ingredients:   { name: string; cost_yuan: number }[];
}

interface RankingResponse {
  stores:      StoreRankingItem[];
  summary:     {
    store_count:          number;
    avg_actual_cost_pct:  number;
    over_budget_count:    number;
  };
  start_date:  string;
  end_date:    string;
}

interface MonthlyReport {
  store_id:          string;
  period_label:      string;
  executive_summary: {
    headline:              string;
    revenue_yuan:          number;
    actual_cost_pct:       number;
    cost_rate_status:      string;
    waste_cost_yuan:       number;
    decision_adoption_pct: number;
    total_saving_yuan:     number;
  };
  weekly_trend_chart: {
    x_axis:          string[];
    cost_rate_data:  number[];
    revenue_data:    number[];
    point_colors:    string[];
  };
}

interface VarianceIngredient {
  item_id:         string;
  name:            string;
  usage_cost_fen:  number;
  usage_cost_yuan: number;
}

interface VarianceDetail {
  store_id:        string;
  start_date:      string;
  end_date:        string;
  actual_cost_fen: number;
  actual_cost_yuan: number;
  revenue_yuan:    number;
  actual_cost_pct: number;
  theoretical_pct: number;
  variance_pct:    number;
  variance_status: string;
  top_ingredients: VarianceIngredient[];
}

// ── 状态颜色工具 ──────────────────────────────────────────────────────────────

const statusColor = (s: string) =>
  s === 'critical' ? '#f5222d' : s === 'warning' ? '#faad14' : '#52c41a';

const statusTag = (s: string) => {
  const map: Record<string, { color: string; text: string }> = {
    ok:       { color: 'success', text: '正常' },
    warning:  { color: 'warning', text: '偏高' },
    critical: { color: 'error',   text: '超标' },
  };
  const cfg = map[s] || { color: 'default', text: s };
  return <Tag color={cfg.color}>{cfg.text}</Tag>;
};

// ════════════════════════════════════════════════════════════════════════════════
// ProfitDashboard — 成本率趋势可视化
// ════════════════════════════════════════════════════════════════════════════════

const ProfitDashboard: React.FC = () => {
  const [loading,       setLoading]       = useState(false);
  const [rankingData,   setRankingData]   = useState<RankingResponse | null>(null);
  const [monthlyReport, setMonthlyReport] = useState<MonthlyReport | null>(null);
  const [varianceData,  setVarianceData]  = useState<VarianceDetail | null>(null);
  const [varianceLoading, setVarianceLoading] = useState(false);
  const [selectedStore, setSelectedStore] = useState<string>('');
  const [reportLoading, setReportLoading] = useState(false);
  const [dateRange,     setDateRange]     = useState<[Dayjs, Dayjs]>([
    dayjs().subtract(30, 'day'),
    dayjs(),
  ]);
  const [reportMonth,   setReportMonth]   = useState<Dayjs>(dayjs().subtract(1, 'month'));

  // ── 加载跨店成本排名 ───────────────────────────────────────────────────────

  const loadRanking = useCallback(async () => {
    setLoading(true);
    try {
      const res = await apiClient.get('/api/v1/hq/food-cost-ranking', {
        params: {
          start_date: dateRange[0].format('YYYY-MM-DD'),
          end_date:   dateRange[1].format('YYYY-MM-DD'),
        },
      });
      setRankingData(res.data);
      // 默认选中成本率最高的门店
      if (res.data?.stores?.length > 0 && !selectedStore) {
        setSelectedStore(res.data.stores[0].store_id);
      }
    } catch (err: any) {
      handleApiError(err, '加载成本排名失败');
    } finally {
      setLoading(false);
    }
  }, [dateRange, selectedStore]);

  // ── 加载单店月度报告 ───────────────────────────────────────────────────────

  const loadMonthlyReport = useCallback(async (storeId: string) => {
    if (!storeId) return;
    setReportLoading(true);
    try {
      const res = await apiClient.get(`/api/v1/reports/monthly/${storeId}`, {
        params: {
          year:  reportMonth.year(),
          month: reportMonth.month() + 1,
        },
      });
      setMonthlyReport(res.data);
    } catch (err: any) {
      handleApiError(err, '加载月度报告失败');
    } finally {
      setReportLoading(false);
    }
  }, [reportMonth]);

  // ── 加载单店食材成本差异明细 ──────────────────────────────────────────────

  const loadVariance = useCallback(async (storeId: string) => {
    if (!storeId) return;
    setVarianceLoading(true);
    try {
      const res = await apiClient.get('/api/v1/hq/food-cost-variance', {
        params: {
          store_id:   storeId,
          start_date: dateRange[0].format('YYYY-MM-DD'),
          end_date:   dateRange[1].format('YYYY-MM-DD'),
        },
      });
      setVarianceData(res.data);
    } catch (err: any) {
      handleApiError(err, '加载食材成本明细失败');
    } finally {
      setVarianceLoading(false);
    }
  }, [dateRange]);

  useEffect(() => { loadRanking(); }, [loadRanking]);
  useEffect(() => {
    if (selectedStore) loadMonthlyReport(selectedStore);
  }, [selectedStore, loadMonthlyReport]);
  useEffect(() => {
    if (selectedStore) loadVariance(selectedStore);
  }, [selectedStore, loadVariance]);

  // ── 跨店成本率排名柱状图 ──────────────────────────────────────────────────

  const rankingChartOption = rankingData ? {
    tooltip: {
      trigger: 'axis',
      formatter: (params: any[]) => {
        const store  = params[0]?.name || '';
        const actual = params[0]?.value || 0;
        const theory = params[1]?.value || 0;
        return `${store}<br/>实际: <b>${actual.toFixed(1)}%</b><br/>理论: ${theory.toFixed(1)}%`;
      },
    },
    legend: { data: ['实际成本率', '理论成本率'] },
    xAxis: {
      type:      'category',
      data:      rankingData.stores.map(s => s.store_name || s.store_id),
      axisLabel: { rotate: 30, fontSize: 12 },
    },
    yAxis: {
      type:      'value',
      name:      '成本率 (%)',
      axisLabel: { formatter: '{value}%' },
    },
    series: [
      {
        name:  '实际成本率',
        type:  'bar',
        data:  rankingData.stores.map(s => ({
          value:     s.actual_cost_pct,
          itemStyle: { color: statusColor(s.variance_status) },
        })),
        label: { show: true, position: 'top', formatter: '{c}%', fontSize: 11 },
      },
      {
        name:      '理论成本率',
        type:      'line',
        data:      rankingData.stores.map(s => s.theoretical_pct),
        lineStyle: { color: '#1890ff', type: 'dashed' },
        symbol:    'circle',
        symbolSize: 6,
        itemStyle: { color: '#1890ff' },
      },
    ],
  } : {};

  // ── 单店周趋势折线图 ──────────────────────────────────────────────────────

  const trendChartOption = monthlyReport?.weekly_trend_chart ? (() => {
    const chart = monthlyReport.weekly_trend_chart;
    return {
      tooltip: {
        trigger: 'axis',
        formatter: (params: any[]) => {
          const week    = params[0]?.name || '';
          const costPct = params[0]?.value || 0;
          const revenue = params[1]?.value || 0;
          return `${week}<br/>成本率: <b>${Number(costPct).toFixed(1)}%</b><br/>营业额: ¥${Number(revenue).toLocaleString()}`;
        },
      },
      legend: { data: ['成本率', '营业额'] },
      xAxis:  { type: 'category', data: chart.x_axis },
      yAxis: [
        {
          type:      'value',
          name:      '成本率 (%)',
          axisLabel: { formatter: '{value}%' },
          splitLine: { lineStyle: { type: 'dashed' } },
        },
        {
          type:      'value',
          name:      '营业额 (¥)',
          axisLabel: { formatter: '¥{value}' },
          splitLine: { show: false },
        },
      ],
      series: [
        {
          name:  '成本率',
          type:  'line',
          yAxisIndex: 0,
          data:  chart.cost_rate_data.map((v: number, i: number) => ({
            value:     v,
            itemStyle: { color: chart.point_colors[i] || '#1890ff' },
          })),
          lineStyle:  { color: '#1890ff', width: 2 },
          areaStyle:  { opacity: 0.1 },
          symbol:     'circle',
          symbolSize: 8,
          markLine:   {
            data: [{ yAxis: 35, name: '警戒线', lineStyle: { color: '#faad14', type: 'dashed' } }],
          },
        },
        {
          name:       '营业额',
          type:       'bar',
          yAxisIndex: 1,
          data:       chart.revenue_data,
          itemStyle:  { color: 'rgba(24,144,255,0.2)' },
          barMaxWidth: 30,
        },
      ],
    };
  })() : {};

  // ── 门店排名表格列 ────────────────────────────────────────────────────────

  const columns = [
    { title: '排名', width: 60, render: (_: any, __: any, i: number) => i + 1 },
    { title: '门店', dataIndex: 'store_name', render: (name: string, row: StoreRankingItem) => (
        <a onClick={() => setSelectedStore(row.store_id)}>{name || row.store_id}</a>
    )},
    {
      title: '实际成本率',
      dataIndex: 'actual_cost_pct',
      render: (v: number, row: StoreRankingItem) => (
        <span style={{ color: statusColor(row.variance_status), fontWeight: 700 }}>
          {v?.toFixed(1)}%
        </span>
      ),
      sorter: (a: StoreRankingItem, b: StoreRankingItem) => b.actual_cost_pct - a.actual_cost_pct,
    },
    {
      title: '理论成本率',
      dataIndex: 'theoretical_pct',
      render: (v: number) => `${v?.toFixed(1) ?? '-'}%`,
    },
    {
      title: '差异',
      dataIndex: 'variance_pct',
      render: (v: number) => {
        const color = v > 5 ? '#f5222d' : v > 2 ? '#faad14' : '#52c41a';
        const icon  = v > 0 ? <RiseOutlined /> : <FallOutlined />;
        return <span style={{ color }}>{icon} {v?.toFixed(1)}%</span>;
      },
      sorter: (a: StoreRankingItem, b: StoreRankingItem) => b.variance_pct - a.variance_pct,
    },
    { title: '状态', dataIndex: 'variance_status', render: statusTag },
    {
      title: '实际成本',
      dataIndex: 'actual_cost_yuan',
      render: (v: number) => `¥${v?.toLocaleString() ?? '-'}`,
    },
  ];

  const summary = rankingData?.summary;
  const execSum = monthlyReport?.executive_summary;

  return (
    <div style={{ padding: 24 }}>
      <Title level={3}>
        <DollarOutlined style={{ marginRight: 8 }} />
        成本率趋势 &amp; 利润分析
      </Title>

      {/* 顶部筛选 */}
      <Card style={{ marginBottom: 16 }}>
        <Space wrap>
          <span>日期区间：</span>
          <DatePicker.RangePicker
            value={dateRange}
            onChange={(v) => v && setDateRange(v as [Dayjs, Dayjs])}
            format="YYYY-MM-DD"
          />
          <Button
            type="primary"
            icon={<ReloadOutlined />}
            onClick={loadRanking}
            loading={loading}
          >
            刷新
          </Button>
        </Space>
      </Card>

      {/* 全局摘要 KPI */}
      {summary && (
        <Row gutter={16} style={{ marginBottom: 16 }}>
          <Col span={8}>
            <Card>
              <Statistic title="参与分析门店数" value={summary.store_count} suffix="家" />
            </Card>
          </Col>
          <Col span={8}>
            <Card>
              <Statistic
                title="平均食材成本率"
                value={summary.avg_actual_cost_pct?.toFixed(1)}
                suffix="%"
                valueStyle={{ color: summary.avg_actual_cost_pct > 35 ? '#f5222d' : '#52c41a' }}
              />
            </Card>
          </Col>
          <Col span={8}>
            <Card>
              <Statistic
                title="超预算门店"
                value={summary.over_budget_count}
                suffix={`/ ${summary.store_count}`}
                valueStyle={{ color: summary.over_budget_count > 0 ? '#f5222d' : '#52c41a' }}
                prefix={summary.over_budget_count > 0 ? <WarningOutlined /> : <CheckCircleOutlined />}
              />
            </Card>
          </Col>
        </Row>
      )}

      <Tabs
        defaultActiveKey="ranking"
        items={[
          {
            key:   'ranking',
            label: '跨店成本排名',
            children: (
              <Spin spinning={loading}>
                {rankingData ? (
                  <>
                    <Card title="成本率排名（实际 vs 理论）" style={{ marginBottom: 16 }}>
                      <ReactECharts option={rankingChartOption} style={{ height: 300 }} />
                    </Card>
                    <Card title="门店明细">
                      <Table
                        dataSource={rankingData.stores}
                        columns={columns}
                        rowKey="store_id"
                        pagination={{ pageSize: 10 }}
                        size="small"
                        onRow={(row) => ({ onClick: () => setSelectedStore(row.store_id) })}
                        rowClassName={(row) =>
                          row.store_id === selectedStore ? 'ant-table-row-selected' : ''
                        }
                      />
                    </Card>
                  </>
                ) : (
                  <Alert message="暂无数据" type="info" />
                )}
              </Spin>
            ),
          },
          {
            key:   'trend',
            label: `单店月度趋势${selectedStore ? ` — ${selectedStore}` : ''}`,
            children: (
              <Spin spinning={reportLoading}>
                <Card style={{ marginBottom: 16 }}>
                  <Space wrap>
                    <span>选择门店：</span>
                    <Select
                      placeholder="选择门店"
                      value={selectedStore || undefined}
                      onChange={setSelectedStore}
                      style={{ width: 200 }}
                    >
                      {rankingData?.stores.map((s) => (
                        <Option key={s.store_id} value={s.store_id}>
                          {s.store_name || s.store_id}
                        </Option>
                      ))}
                    </Select>
                    <span>报告月份：</span>
                    <DatePicker
                      picker="month"
                      value={reportMonth}
                      onChange={(v) => v && setReportMonth(v)}
                      format="YYYY年MM月"
                      disabledDate={(d) => d && d > dayjs().endOf('month')}
                    />
                    <Button
                      icon={<ReloadOutlined />}
                      onClick={() => loadMonthlyReport(selectedStore)}
                      loading={reportLoading}
                      disabled={!selectedStore}
                    >
                      刷新
                    </Button>
                    {selectedStore && (
                      <Button
                        type="link"
                        href={`/api/v1/reports/monthly/${selectedStore}/html?year=${reportMonth.year()}&month=${reportMonth.month() + 1}`}
                        target="_blank"
                      >
                        打印 PDF
                      </Button>
                    )}
                  </Space>
                </Card>

                {monthlyReport ? (
                  <>
                    {/* 高管摘要 */}
                    {execSum && (
                      <Alert
                        message={execSum.headline}
                        type={execSum.cost_rate_status === 'critical' ? 'error' : execSum.cost_rate_status === 'warning' ? 'warning' : 'success'}
                        showIcon
                        style={{ marginBottom: 16 }}
                      />
                    )}

                    {execSum && (
                      <Row gutter={16} style={{ marginBottom: 16 }}>
                        <Col span={6}>
                          <Card size="small">
                            <Statistic
                              title="月营业额"
                              value={execSum.revenue_yuan}
                              prefix="¥"
                              precision={0}
                            />
                          </Card>
                        </Col>
                        <Col span={6}>
                          <Card size="small">
                            <Statistic
                              title="食材成本率"
                              value={execSum.actual_cost_pct?.toFixed(1)}
                              suffix="%"
                              valueStyle={{ color: statusColor(execSum.cost_rate_status) }}
                            />
                          </Card>
                        </Col>
                        <Col span={6}>
                          <Card size="small">
                            <Statistic
                              title="决策采纳率"
                              value={execSum.decision_adoption_pct?.toFixed(0)}
                              suffix="%"
                            />
                          </Card>
                        </Col>
                        <Col span={6}>
                          <Card size="small">
                            <Statistic
                              title="决策节省金额"
                              value={execSum.total_saving_yuan}
                              prefix="¥"
                              precision={0}
                              valueStyle={{ color: '#52c41a' }}
                            />
                          </Card>
                        </Col>
                      </Row>
                    )}

                    {/* 周趋势图 */}
                    <Card title={`${monthlyReport.period_label} 成本率周趋势`} style={{ marginBottom: 16 }}>
                      <ReactECharts option={trendChartOption} style={{ height: 320 }} />
                      <Text type="secondary" style={{ fontSize: 12 }}>
                        橙色虚线为 35% 警戒线；柱状为营业额（右轴）；点颜色：绿=正常 橙=偏高 红=超标
                      </Text>
                    </Card>
                  </>
                ) : (
                  !reportLoading && selectedStore && (
                    <Alert message="请先选择门店或点击刷新" type="info" />
                  )
                )}
              </Spin>
            ),
          },
          {
            key:   'variance',
            label: (
              <span>
                <SearchOutlined />
                单店食材明细{selectedStore ? ` — ${rankingData?.stores.find(s => s.store_id === selectedStore)?.store_name || selectedStore}` : ''}
              </span>
            ),
            children: (
              <Spin spinning={varianceLoading}>
                {/* 门店选择 */}
                <Card style={{ marginBottom: 16 }}>
                  <Space wrap>
                    <span>选择门店：</span>
                    <Select
                      placeholder="选择门店"
                      value={selectedStore || undefined}
                      onChange={(v) => { setSelectedStore(v); loadVariance(v); }}
                      style={{ width: 200 }}
                    >
                      {rankingData?.stores.map((s) => (
                        <Option key={s.store_id} value={s.store_id}>
                          {s.store_name || s.store_id}
                        </Option>
                      ))}
                    </Select>
                    <Button
                      icon={<ReloadOutlined />}
                      onClick={() => selectedStore && loadVariance(selectedStore)}
                      loading={varianceLoading}
                      disabled={!selectedStore}
                    >
                      刷新
                    </Button>
                    {varianceData && (
                      <Text type="secondary" style={{ fontSize: 12 }}>
                        {varianceData.start_date} 至 {varianceData.end_date}
                      </Text>
                    )}
                  </Space>
                </Card>

                {varianceData ? (
                  <>
                    {/* KPI 卡片 */}
                    <Row gutter={16} style={{ marginBottom: 16 }}>
                      <Col span={6}>
                        <Card size="small">
                          <Statistic
                            title="实际食材成本"
                            value={varianceData.actual_cost_yuan}
                            prefix="¥"
                            precision={0}
                            valueStyle={{ color: '#1677ff' }}
                          />
                        </Card>
                      </Col>
                      <Col span={6}>
                        <Card size="small">
                          <Statistic
                            title="实际成本率"
                            value={varianceData.actual_cost_pct?.toFixed(1)}
                            suffix="%"
                            valueStyle={{ color: statusColor(varianceData.variance_status) }}
                          />
                          {statusTag(varianceData.variance_status)}
                        </Card>
                      </Col>
                      <Col span={6}>
                        <Card size="small">
                          <Statistic
                            title="理论成本率"
                            value={varianceData.theoretical_pct?.toFixed(1)}
                            suffix="%"
                            valueStyle={{ color: '#52c41a' }}
                          />
                        </Card>
                      </Col>
                      <Col span={6}>
                        <Card size="small">
                          <Statistic
                            title="实际 vs 理论差异"
                            value={varianceData.variance_pct?.toFixed(1)}
                            suffix="%"
                            prefix={varianceData.variance_pct > 0 ? <RiseOutlined /> : <FallOutlined />}
                            valueStyle={{
                              color: varianceData.variance_pct > 5 ? '#f5222d'
                                   : varianceData.variance_pct > 2 ? '#faad14'
                                   : '#52c41a',
                            }}
                          />
                        </Card>
                      </Col>
                    </Row>

                    {/* Top 10 食材用料明细表 */}
                    <Card
                      title={
                        <Space>
                          <DollarOutlined style={{ color: '#1677ff' }} />
                          Top 10 食材用料成本（按金额排序）
                        </Space>
                      }
                      extra={
                        <Text type="secondary">
                          营业额 ¥{varianceData.revenue_yuan?.toLocaleString('zh-CN', { minimumFractionDigits: 0 })}
                        </Text>
                      }
                    >
                      <Table
                        dataSource={varianceData.top_ingredients.map((item, idx) => ({
                          ...item,
                          rank: idx + 1,
                          cost_share_pct: varianceData.actual_cost_fen > 0
                            ? Math.round(item.usage_cost_fen / varianceData.actual_cost_fen * 1000) / 10
                            : 0,
                        }))}
                        rowKey="item_id"
                        pagination={false}
                        size="middle"
                        locale={{ emptyText: '暂无食材用料数据' }}
                        columns={[
                          {
                            title: '排名',
                            dataIndex: 'rank',
                            width: 56,
                            render: (rank: number) => (
                              <span style={{
                                display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                                width: 28, height: 28, borderRadius: '50%',
                                background: rank <= 3 ? '#1677ff' : '#d9d9d9',
                                color: rank <= 3 ? '#fff' : '#666',
                                fontWeight: 'bold', fontSize: 13,
                              }}>
                                {rank}
                              </span>
                            ),
                          },
                          {
                            title: '食材名称',
                            dataIndex: 'name',
                            render: (name: string) => <Text strong>{name}</Text>,
                          },
                          {
                            title: '用料成本',
                            dataIndex: 'usage_cost_yuan',
                            sorter: (a: any, b: any) => b.usage_cost_yuan - a.usage_cost_yuan,
                            render: (yuan: number) => (
                              <Text strong style={{ color: '#1677ff' }}>
                                ¥{yuan?.toLocaleString('zh-CN', { minimumFractionDigits: 0 })}
                              </Text>
                            ),
                          },
                          {
                            title: '占实际成本',
                            dataIndex: 'cost_share_pct',
                            render: (pct: number) => (
                              <Space>
                                <Progress
                                  percent={pct}
                                  size="small"
                                  style={{ width: 90 }}
                                  showInfo={false}
                                  strokeColor={pct >= 20 ? '#f5222d' : pct >= 10 ? '#faad14' : '#1677ff'}
                                />
                                <Text style={{ fontSize: 12 }}>{pct?.toFixed(1)}%</Text>
                              </Space>
                            ),
                          },
                        ]}
                      />
                    </Card>
                  </>
                ) : (
                  !varianceLoading && selectedStore && (
                    <Alert message="请点击刷新加载食材成本明细" type="info" />
                  )
                )}

                {!selectedStore && (
                  <Alert message="请在「跨店成本排名」中点击一家门店，或在上方下拉菜单中选择门店" type="info" />
                )}
              </Spin>
            ),
          },
        ]}
      />
    </div>
  );
};

export default ProfitDashboard;
