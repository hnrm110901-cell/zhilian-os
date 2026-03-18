/**
 * 全渠道营收分析页 — /platform/omni-channel
 *
 * 功能区：
 *   1. 顶部 KPI 行：总营收、订单量、客单价、净利润
 *   2. 渠道分解卡片：每渠道收入/订单/佣金/净收入 + 占比
 *   3. 营收趋势表（按日期 × 渠道），支持 7天/30天/自定义
 *   4. 渠道对比表
 *   5. 利润瀑布：毛收入 → 扣佣 → 扣配送 → 净利润
 *   6. 峰时热力图：小时 × 渠道 订单量
 *
 * 后端 API: /api/v1/omni-channel/*
 */
import React, { useState, useEffect, useCallback } from 'react';
import {
  Card, Statistic, Row, Col, Select, Button, Table, Tag,
  DatePicker, Spin, Empty, Typography, Space, message,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import {
  ReloadOutlined, DollarOutlined, ShoppingCartOutlined,
  RiseOutlined, FundOutlined,
} from '@ant-design/icons';
import dayjs from 'dayjs';
import type { Dayjs } from 'dayjs';
import { apiClient } from '../../services/api';
import styles from './OmniChannelPage.module.css';

const { Title, Text } = Typography;
const { RangePicker } = DatePicker;

// ── 类型 ─────────────────────────────────────────────────────────

interface ChannelItem {
  channel: string;
  channel_label: string;
  order_count: number;
  gross_revenue_yuan: number;
  commission_yuan: number;
  commission_rate: number;
  delivery_cost_yuan: number;
  packaging_cost_yuan: number;
  net_revenue_yuan: number;
  share_pct: number;
}

interface RevenueTotals {
  order_count: number;
  gross_revenue_yuan: number;
  commission_yuan: number;
  delivery_cost_yuan: number;
  net_revenue_yuan: number;
}

interface RevenueResponse {
  period: string;
  store_id: string | null;
  total: RevenueTotals;
  channels: ChannelItem[];
}

interface TrendDayChannels {
  [channel: string]: { order_count: number; revenue_yuan: number };
}

interface TrendDay {
  date: string;
  channels: TrendDayChannels;
  total_revenue_yuan: number;
}

interface TrendResponse {
  days: number;
  start_date: string;
  end_date: string;
  trend: TrendDay[];
}

interface ComparisonItem {
  channel: string;
  channel_label: string;
  order_count: number;
  total_revenue_yuan: number;
  avg_order_yuan: number;
  commission_rate_pct: number;
  net_revenue_yuan: number;
  peak_hour: number | null;
  share_pct: number;
}

interface ComparisonResponse {
  period: string;
  comparisons: ComparisonItem[];
}

interface ProfitSummary {
  gross_revenue_yuan: number;
  commission_yuan: number;
  delivery_cost_yuan: number;
  packaging_cost_yuan: number;
  net_profit_yuan: number;
  overall_margin_pct: number;
}

interface ProfitResponse {
  period: string;
  summary: ProfitSummary;
  channels: any[];
}

interface HeatmapRow {
  hour: number;
  dine_in: number;
  eleme: number;
  meituan: number;
  douyin: number;
  pickup: number;
  corporate: number;
  total: number;
}

interface PeakResponse {
  period: string;
  channels: string[];
  channel_labels: Record<string, string>;
  heatmap: HeatmapRow[];
}

// ── 常量 ─────────────────────────────────────────────────────────

const CHANNEL_COLORS: Record<string, string> = {
  dine_in: '#1890ff',
  eleme: '#0095ff',
  meituan: '#ffc300',
  douyin: '#000000',
  pickup: '#52c41a',
  corporate: '#722ed1',
};

const ALL_CHANNELS = ['dine_in', 'eleme', 'meituan', 'douyin', 'pickup', 'corporate'];

const CHANNEL_LABELS: Record<string, string> = {
  dine_in: '堂食',
  eleme: '饿了么',
  meituan: '美团',
  douyin: '抖音团购',
  pickup: '自提',
  corporate: '企业团餐',
};

// ── 工具函数 ─────────────────────────────────────────────────────

function fmtYuan(val: number): string {
  return `¥${val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function heatColor(count: number, max: number): string {
  if (max === 0 || count === 0) return 'transparent';
  const intensity = Math.min(count / max, 1);
  const r = 255;
  const g = Math.round(255 - intensity * 148);
  const b = Math.round(255 - intensity * 211);
  return `rgb(${r}, ${g}, ${b})`;
}

// ── 组件 ─────────────────────────────────────────────────────────

const OmniChannelPage: React.FC = () => {
  // 过滤器状态
  const [brandId, setBrandId] = useState<string>('default');
  const [storeId, setStoreId] = useState<string | undefined>(undefined);
  const [dateRange, setDateRange] = useState<[Dayjs, Dayjs]>([
    dayjs().subtract(29, 'day'),
    dayjs(),
  ]);
  const [trendDays, setTrendDays] = useState<number>(30);

  // 数据状态
  const [revenue, setRevenue] = useState<RevenueResponse | null>(null);
  const [trend, setTrend] = useState<TrendResponse | null>(null);
  const [comparison, setComparison] = useState<ComparisonResponse | null>(null);
  const [profit, setProfit] = useState<ProfitResponse | null>(null);
  const [peak, setPeak] = useState<PeakResponse | null>(null);

  // 加载状态
  const [loading, setLoading] = useState(false);
  const [storeOptions, setStoreOptions] = useState<{ label: string; value: any }[]>([]);
  useEffect(() => {
    apiClient.get('/api/v1/stores').then((res: any) => {
      const list: any[] = res.stores || res || [];
      setStoreOptions(list.map((s: any) => ({ label: s.name || s.store_id || s.id, value: s.store_id || s.id })));
    }).catch(() => {});
  }, []);

  // ── 数据拉取 ───────────────────────────────────────────────────

  const fetchAll = useCallback(async () => {
    setLoading(true);
    const startStr = dateRange[0].format('YYYY-MM-DD');
    const endStr = dateRange[1].format('YYYY-MM-DD');
    const baseParams: Record<string, string> = {
      brand_id: brandId,
      start_date: startStr,
      end_date: endStr,
    };
    if (storeId) baseParams.store_id = storeId;

    try {
      const [revData, trendData, compData, profitData, peakData] = await Promise.all([
        apiClient.get<RevenueResponse>('/api/v1/omni-channel/revenue', { params: baseParams }),
        apiClient.get<TrendResponse>('/api/v1/omni-channel/trend', {
          params: { brand_id: brandId, days: trendDays, ...(storeId ? { store_id: storeId } : {}) },
        }),
        apiClient.get<ComparisonResponse>('/api/v1/omni-channel/comparison', {
          params: { brand_id: brandId, start_date: startStr, end_date: endStr },
        }),
        apiClient.get<ProfitResponse>('/api/v1/omni-channel/profit', { params: baseParams }),
        apiClient.get<PeakResponse>('/api/v1/omni-channel/peak-hours', {
          params: { brand_id: brandId, ...(storeId ? { store_id: storeId } : {}) },
        }),
      ]);

      setRevenue(revData);
      setTrend(trendData);
      setComparison(compData);
      setProfit(profitData);
      setPeak(peakData);
    } catch (err: any) {
      message.error('加载全渠道数据失败');
      console.error(err);
    } finally {
      setLoading(false);
    }
  }, [brandId, storeId, dateRange, trendDays]);

  useEffect(() => {
    fetchAll();
  }, [fetchAll]);

  // ── 渠道对比表列定义 ──────────────────────────────────────────

  const comparisonColumns: ColumnsType<ComparisonItem> = [
    {
      title: '渠道',
      dataIndex: 'channel_label',
      key: 'channel',
      render: (label: string, record) => (
        <Space>
          <span
            style={{
              display: 'inline-block',
              width: 10,
              height: 10,
              borderRadius: '50%',
              background: CHANNEL_COLORS[record.channel] || '#999',
            }}
          />
          {label}
        </Space>
      ),
    },
    {
      title: '订单数',
      dataIndex: 'order_count',
      key: 'orders',
      sorter: (a, b) => a.order_count - b.order_count,
      align: 'right',
    },
    {
      title: '营收',
      dataIndex: 'total_revenue_yuan',
      key: 'revenue',
      render: (v: number) => fmtYuan(v),
      sorter: (a, b) => a.total_revenue_yuan - b.total_revenue_yuan,
      align: 'right',
    },
    {
      title: '客单价',
      dataIndex: 'avg_order_yuan',
      key: 'avg',
      render: (v: number) => fmtYuan(v),
      sorter: (a, b) => a.avg_order_yuan - b.avg_order_yuan,
      align: 'right',
    },
    {
      title: '佣金率',
      dataIndex: 'commission_rate_pct',
      key: 'commission',
      render: (v: number) => `${v}%`,
      align: 'right',
    },
    {
      title: '净收入',
      dataIndex: 'net_revenue_yuan',
      key: 'net',
      render: (v: number) => fmtYuan(v),
      sorter: (a, b) => a.net_revenue_yuan - b.net_revenue_yuan,
      align: 'right',
    },
    {
      title: '占比',
      dataIndex: 'share_pct',
      key: 'share',
      render: (v: number) => <Tag color="orange">{v}%</Tag>,
      align: 'right',
    },
    {
      title: '峰值时段',
      dataIndex: 'peak_hour',
      key: 'peak',
      render: (v: number | null) => (v !== null ? `${v}:00` : '-'),
      align: 'center',
    },
  ];

  // ── 趋势表列定义 ──────────────────────────────────────────────

  const trendColumns: ColumnsType<TrendDay> = [
    {
      title: '日期',
      dataIndex: 'date',
      key: 'date',
      fixed: 'left',
      width: 110,
    },
    ...ALL_CHANNELS.map((ch) => ({
      title: CHANNEL_LABELS[ch],
      key: ch,
      align: 'right' as const,
      render: (_: any, record: TrendDay) => {
        const chData = record.channels[ch];
        if (!chData || chData.revenue_yuan === 0) return <Text type="secondary">-</Text>;
        return (
          <span>
            {fmtYuan(chData.revenue_yuan)}
            <br />
            <Text type="secondary" style={{ fontSize: 11 }}>{chData.order_count}单</Text>
          </span>
        );
      },
    })),
    {
      title: '合计',
      dataIndex: 'total_revenue_yuan',
      key: 'total',
      render: (v: number) => <strong>{fmtYuan(v)}</strong>,
      align: 'right',
      fixed: 'right',
      width: 120,
    },
  ];

  // ── 峰时热力图最大值 ──────────────────────────────────────────

  const peakMax = peak
    ? Math.max(...peak.heatmap.flatMap((row) => ALL_CHANNELS.map((ch) => (row as any)[ch] as number)), 1)
    : 1;

  // ── 渲染 ──────────────────────────────────────────────────────

  if (loading && !revenue) {
    return (
      <div className={styles.spinCenter}>
        <Spin size="large" tip="加载全渠道数据..." />
      </div>
    );
  }

  const totals = revenue?.total;
  const avgOrderYuan = totals && totals.order_count > 0
    ? (totals.gross_revenue_yuan / totals.order_count)
    : 0;

  return (
    <div className={styles.page}>
      {/* ── 页头 ──────────────────────────────────────────────── */}
      <div className={styles.pageHeader}>
        <div>
          <h1 className={styles.pageTitle}>全渠道营收分析</h1>
          <span className={styles.pageSubtitle}>
            统一视图：堂食 + 外卖 + 团购 + 自提 + 企业团餐
          </span>
        </div>
        <Button icon={<ReloadOutlined />} onClick={fetchAll} loading={loading}>
          刷新
        </Button>
      </div>

      {/* ── 过滤栏 ────────────────────────────────────────────── */}
      <div className={styles.filterBar}>
        <Select
          value={brandId}
          onChange={setBrandId}
          style={{ width: 160 }}
          placeholder="选择品牌"
          options={[{ label: '默认品牌', value: 'default' }]}
        />
        <Select
          value={storeId}
          onChange={setStoreId}
          allowClear
          style={{ width: 160 }}
          placeholder="全部门店"
          options={[
            { label: '全部门店', value: undefined as any },
            ...storeOptions,
          ]}
        />
        <RangePicker
          value={dateRange}
          onChange={(vals) => {
            if (vals && vals[0] && vals[1]) {
              setDateRange([vals[0], vals[1]]);
            }
          }}
        />
      </div>

      {/* ── KPI 统计行 ────────────────────────────────────────── */}
      <Row gutter={16} className={styles.kpiRow}>
        <Col xs={12} sm={6}>
          <Card className={styles.kpiCard}>
            <Statistic
              title="总营收"
              value={totals?.gross_revenue_yuan ?? 0}
              prefix={<DollarOutlined />}
              precision={2}
              valueStyle={{ color: '#ff6b2c', fontWeight: 700 }}
              formatter={(val) => `¥${Number(val).toLocaleString('zh-CN', { minimumFractionDigits: 2 })}`}
            />
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card className={styles.kpiCard}>
            <Statistic
              title="总订单"
              value={totals?.order_count ?? 0}
              prefix={<ShoppingCartOutlined />}
              valueStyle={{ fontWeight: 700 }}
            />
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card className={styles.kpiCard}>
            <Statistic
              title="平均客单价"
              value={avgOrderYuan}
              prefix={<RiseOutlined />}
              precision={2}
              valueStyle={{ fontWeight: 700 }}
              formatter={(val) => `¥${Number(val).toLocaleString('zh-CN', { minimumFractionDigits: 2 })}`}
            />
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card className={styles.kpiCard}>
            <Statistic
              title="净利润（扣佣后）"
              value={totals?.net_revenue_yuan ?? 0}
              prefix={<FundOutlined />}
              precision={2}
              valueStyle={{ color: '#52c41a', fontWeight: 700 }}
              formatter={(val) => `¥${Number(val).toLocaleString('zh-CN', { minimumFractionDigits: 2 })}`}
            />
          </Card>
        </Col>
      </Row>

      {/* ── 渠道分解卡片 ──────────────────────────────────────── */}
      <h2 className={styles.sectionTitle}>渠道分解</h2>
      {revenue && revenue.channels.length > 0 ? (
        <div className={styles.channelGrid}>
          {revenue.channels.map((ch) => (
            <Card
              key={ch.channel}
              className={styles.channelCard}
              style={{ borderTop: `3px solid ${CHANNEL_COLORS[ch.channel] || '#999'}` }}
            >
              <div className={styles.channelName}>{ch.channel_label}</div>
              <div className={styles.channelRevenue}>{fmtYuan(ch.gross_revenue_yuan)}</div>
              <span className={styles.channelShare}>{ch.share_pct}%</span>
              <div className={styles.channelMeta}>
                <span>订单: {ch.order_count}</span>
                <span>佣金: {fmtYuan(ch.commission_yuan)} ({ch.commission_rate}%)</span>
                <span>配送: {fmtYuan(ch.delivery_cost_yuan)}</span>
                <span>净收入: {fmtYuan(ch.net_revenue_yuan)}</span>
              </div>
            </Card>
          ))}
        </div>
      ) : (
        <Empty description="暂无渠道数据" />
      )}

      {/* ── 利润瀑布 ──────────────────────────────────────────── */}
      {profit && (
        <>
          <h2 className={styles.sectionTitle}>利润瀑布</h2>
          <div className={styles.waterfallRow}>
            <div className={`${styles.waterfallStep} ${styles.gross}`}>
              <div className={styles.waterfallLabel}>毛收入</div>
              <div className={styles.waterfallValue}>
                {fmtYuan(profit.summary.gross_revenue_yuan)}
              </div>
            </div>
            <span className={styles.waterfallArrow}>→</span>
            <div className={`${styles.waterfallStep} ${styles.deduction}`}>
              <div className={styles.waterfallLabel}>平台佣金</div>
              <div className={styles.waterfallValue}>
                -{fmtYuan(profit.summary.commission_yuan)}
              </div>
            </div>
            <span className={styles.waterfallArrow}>→</span>
            <div className={`${styles.waterfallStep} ${styles.deduction}`}>
              <div className={styles.waterfallLabel}>配送费</div>
              <div className={styles.waterfallValue}>
                -{fmtYuan(profit.summary.delivery_cost_yuan)}
              </div>
            </div>
            <span className={styles.waterfallArrow}>→</span>
            <div className={`${styles.waterfallStep} ${styles.deduction}`}>
              <div className={styles.waterfallLabel}>包材费</div>
              <div className={styles.waterfallValue}>
                -{fmtYuan(profit.summary.packaging_cost_yuan)}
              </div>
            </div>
            <span className={styles.waterfallArrow}>→</span>
            <div className={`${styles.waterfallStep} ${styles.net}`}>
              <div className={styles.waterfallLabel}>
                净利润（{profit.summary.overall_margin_pct}%）
              </div>
              <div className={styles.waterfallValue}>
                {fmtYuan(profit.summary.net_profit_yuan)}
              </div>
            </div>
          </div>
        </>
      )}

      {/* ── 渠道对比表 ────────────────────────────────────────── */}
      {comparison && (
        <>
          <h2 className={styles.sectionTitle}>渠道对比</h2>
          <Table<ComparisonItem>
            columns={comparisonColumns}
            dataSource={comparison.comparisons}
            rowKey="channel"
            pagination={false}
            size="middle"
            scroll={{ x: 800 }}
            style={{ marginBottom: 24 }}
          />
        </>
      )}

      {/* ── 营收趋势 ─────────────────────────────────────────── */}
      <div className={styles.trendSection}>
        <h2 className={styles.sectionTitle}>营收趋势</h2>
        <div className={styles.periodSelector}>
          <Button
            type={trendDays === 7 ? 'primary' : 'default'}
            size="small"
            onClick={() => setTrendDays(7)}
          >
            7天
          </Button>
          <Button
            type={trendDays === 30 ? 'primary' : 'default'}
            size="small"
            onClick={() => setTrendDays(30)}
          >
            30天
          </Button>
          <Button
            type={trendDays === 90 ? 'primary' : 'default'}
            size="small"
            onClick={() => setTrendDays(90)}
          >
            90天
          </Button>
        </div>
        {trend && (
          <div className={styles.trendTable}>
            <Table<TrendDay>
              columns={trendColumns}
              dataSource={trend.trend}
              rowKey="date"
              pagination={{ pageSize: 10 }}
              size="small"
              scroll={{ x: 900 }}
            />
          </div>
        )}
      </div>

      {/* ── 峰时热力图 ────────────────────────────────────────── */}
      {peak && (
        <>
          <h2 className={styles.sectionTitle}>峰时热力图（近7天）</h2>
          <div className={styles.heatmapWrap}>
            <table className={styles.heatmapTable}>
              <thead>
                <tr>
                  <th>渠道 \ 时段</th>
                  {Array.from({ length: 24 }, (_, i) => (
                    <th key={i}>{i}时</th>
                  ))}
                  <th>合计</th>
                </tr>
              </thead>
              <tbody>
                {ALL_CHANNELS.map((ch) => {
                  const rowTotal = peak.heatmap.reduce(
                    (sum, row) => sum + ((row as any)[ch] as number),
                    0,
                  );
                  return (
                    <tr key={ch}>
                      <td className={styles.channelHeader}>
                        {CHANNEL_LABELS[ch]}
                      </td>
                      {peak.heatmap.map((row) => {
                        const count = (row as any)[ch] as number;
                        return (
                          <td key={row.hour}>
                            <span
                              className={styles.heatCell}
                              style={{ background: heatColor(count, peakMax) }}
                              title={`${CHANNEL_LABELS[ch]} ${row.hour}时: ${count}单`}
                            >
                              {count > 0 ? count : ''}
                            </span>
                          </td>
                        );
                      })}
                      <td><strong>{rowTotal}</strong></td>
                    </tr>
                  );
                })}
                {/* 合计行 */}
                <tr>
                  <td className={styles.channelHeader}><strong>合计</strong></td>
                  {peak.heatmap.map((row) => (
                    <td key={row.hour}><strong>{row.total}</strong></td>
                  ))}
                  <td>
                    <strong>
                      {peak.heatmap.reduce((s, r) => s + r.total, 0)}
                    </strong>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
};

export default OmniChannelPage;
