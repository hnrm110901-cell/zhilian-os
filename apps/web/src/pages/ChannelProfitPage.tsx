import React, { useState, useEffect, useCallback } from 'react';
import {
  Card, Row, Col, Select, Statistic, Table, Tag, Button,
  Typography, Space, Spin, Progress, Radio,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import {
  ShopOutlined, ReloadOutlined, RiseOutlined, FallOutlined,
} from '@ant-design/icons';
import ReactECharts from 'echarts-for-react';
import { apiClient } from '../services/api';
import { handleApiError } from '../utils/message';

const { Title } = Typography;
const { Option } = Select;

interface ChannelDish {
  dish_id: string;
  dish_name: string;
  channel: string;
  store_id: string;
  price_yuan: number;
  revenue_yuan: number;
  bom_cost_yuan: number;
  packaging_cost_yuan: number;
  delivery_cost_yuan: number;
  total_cost_yuan: number;
  gross_profit_yuan: number;
  gross_margin_pct: number;
  label: string;
  bom_source_ids: string[];
}

const LABEL_COLOR: Record<string, string> = {
  '赚钱': 'success',
  '勉强': 'warning',
  '亏钱': 'error',
};

const CHANNEL_NAMES: Record<string, string> = {
  meituan: '美团外卖',
  eleme: '饿了么',
  dineIn: '堂食',
  takeaway: '自取',
};

const ChannelProfitPage: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [stores, setStores] = useState<any[]>([]);
  const [storeId, setStoreId] = useState(localStorage.getItem('store_id') || '');
  const [items, setItems] = useState<ChannelDish[]>([]);
  const [labelFilter, setLabelFilter] = useState<string>('all');

  const loadStores = useCallback(async () => {
    try {
      const res = await apiClient.get('/api/v1/stores');
      setStores(res.stores || res || []);
    } catch { /* ignore */ }
  }, []);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const url =
        labelFilter !== 'all'
          ? `/api/v1/channel-profit/${storeId}/labels?label=${encodeURIComponent(labelFilter)}`
          : `/api/v1/channel-profit/${storeId}`;
      const res = await apiClient.get<ChannelDish[]>(url);
      setItems(Array.isArray(res) ? res : (res as any).data ?? []);
    } catch (err: any) {
      handleApiError(err, '加载渠道毛利失败');
    } finally {
      setLoading(false);
    }
  }, [storeId, labelFilter]);

  useEffect(() => { loadStores(); }, [loadStores]);
  useEffect(() => { loadData(); }, [loadData]);

  // ── 统计 ──────────────────────────────────────────────────────────────────
  const profitCount  = items.filter(d => d.label === '赚钱').length;
  const breakEven    = items.filter(d => d.label === '勉强').length;
  const lossCount    = items.filter(d => d.label === '亏钱').length;
  const avgMargin    = items.length
    ? Math.round(items.reduce((s, d) => s + d.gross_margin_pct * 100, 0) / items.length)
    : 0;

  // ── 图表：各渠道平均毛利率 ────────────────────────────────────────────────
  const channelMap: Record<string, number[]> = {};
  items.forEach(d => {
    if (!channelMap[d.channel]) channelMap[d.channel] = [];
    channelMap[d.channel].push(d.gross_margin_pct * 100);
  });
  const channelLabels = Object.keys(channelMap);
  const channelAvg = channelLabels.map(
    ch => Math.round(channelMap[ch].reduce((s, v) => s + v, 0) / channelMap[ch].length)
  );

  const barOption = {
    tooltip: { trigger: 'axis', formatter: (p: any) => `${p[0].name}: ${p[0].value}%` },
    xAxis: {
      type: 'category',
      data: channelLabels.map(ch => CHANNEL_NAMES[ch] || ch),
      axisLabel: { fontSize: 12 },
    },
    yAxis: { type: 'value', name: '平均毛利率 (%)', max: 100 },
    series: [{
      type: 'bar',
      data: channelAvg.map((v, i) => ({
        value: v,
        itemStyle: { color: v >= 40 ? '#1A7A52' : v >= 20 ? '#faad14' : '#C53030' },
        label: { show: true, position: 'top', formatter: `${v}%` },
      })),
    }],
  };

  // ── 饼图：赚钱/勉强/亏钱分布 ─────────────────────────────────────────────
  const pieOption = {
    tooltip: { trigger: 'item', formatter: '{b}: {c} 道 ({d}%)' },
    legend: { bottom: 0 },
    series: [{
      type: 'pie',
      radius: ['40%', '70%'],
      data: [
        { value: profitCount,  name: '赚钱', itemStyle: { color: '#1A7A52' } },
        { value: breakEven,    name: '勉强', itemStyle: { color: '#faad14' } },
        { value: lossCount,    name: '亏钱', itemStyle: { color: '#C53030' } },
      ],
    }],
  };

  // ── 表格 ──────────────────────────────────────────────────────────────────
  const columns: ColumnsType<ChannelDish> = [
    { title: '菜品', dataIndex: 'dish_name', width: 140, ellipsis: true },
    {
      title: '渠道',
      dataIndex: 'channel',
      width: 90,
      render: (v: string) => CHANNEL_NAMES[v] || v,
    },
    { title: '售价', dataIndex: 'price_yuan', width: 80, render: (v: number) => `¥${v.toFixed(2)}` },
    { title: '到手', dataIndex: 'revenue_yuan', width: 80, render: (v: number) => `¥${v.toFixed(2)}` },
    { title: '食材成本', dataIndex: 'bom_cost_yuan', width: 80, render: (v: number) => `¥${v.toFixed(2)}` },
    { title: '总成本', dataIndex: 'total_cost_yuan', width: 80, render: (v: number) => `¥${v.toFixed(2)}` },
    { title: '毛利', dataIndex: 'gross_profit_yuan', width: 80, render: (v: number) => `¥${v.toFixed(2)}` },
    {
      title: '毛利率',
      dataIndex: 'gross_margin_pct',
      width: 110,
      sorter: (a, b) => a.gross_margin_pct - b.gross_margin_pct,
      render: (v: number) => {
        const pct = Math.round(v * 100);
        return (
          <Progress
            percent={pct}
            size="small"
            status={pct >= 40 ? 'success' : pct >= 20 ? 'normal' : 'exception'}
            format={p => `${p}%`}
          />
        );
      },
    },
    {
      title: '标注',
      dataIndex: 'label',
      width: 70,
      render: (v: string) => <Tag color={LABEL_COLOR[v] || 'default'}>{v}</Tag>,
    },
  ];

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <Title level={4} style={{ margin: 0 }}><ShopOutlined /> 渠道毛利看板</Title>
        <Space>
          <Select value={storeId} onChange={setStoreId} style={{ width: 160 }}>
            {stores.length > 0
              ? stores.map((s: any) => (
                  <Option key={s.id || s.store_id} value={s.id || s.store_id}>{s.name}</Option>
                ))
          </Select>
          <Button icon={<ReloadOutlined />} onClick={loadData}>刷新</Button>
        </Space>
      </div>

      <Spin spinning={loading}>
        {/* ── KPI 卡片 ── */}
        <Row gutter={16} style={{ marginBottom: 16 }}>
          <Col span={6}>
            <Card>
              <Statistic title="分析菜品×渠道数" value={items.length} suffix="条" />
            </Card>
          </Col>
          <Col span={6}>
            <Card>
              <Statistic
                title="平均毛利率"
                value={avgMargin}
                suffix="%"
                valueStyle={{ color: avgMargin >= 40 ? '#1A7A52' : '#faad14' }}
              />
            </Card>
          </Col>
          <Col span={6}>
            <Card>
              <Statistic
                title="盈利菜品"
                value={profitCount}
                suffix={`/ ${items.length}`}
                prefix={<RiseOutlined style={{ color: '#1A7A52' }} />}
                valueStyle={{ color: '#1A7A52' }}
              />
            </Card>
          </Col>
          <Col span={6}>
            <Card>
              <Statistic
                title="亏损菜品"
                value={lossCount}
                suffix={`/ ${items.length}`}
                prefix={<FallOutlined style={{ color: '#C53030' }} />}
                valueStyle={{ color: lossCount > 0 ? '#C53030' : undefined }}
              />
            </Card>
          </Col>
        </Row>

        {/* ── 图表 ── */}
        <Row gutter={16} style={{ marginBottom: 16 }}>
          <Col span={14}>
            <Card title="各渠道平均毛利率" size="small">
              {channelLabels.length > 0
                ? <ReactECharts option={barOption} style={{ height: 240 }} />
                : <div style={{ textAlign: 'center', padding: 60, color: '#999' }}>暂无数据</div>}
            </Card>
          </Col>
          <Col span={10}>
            <Card title="盈亏分布" size="small">
              {items.length > 0
                ? <ReactECharts option={pieOption} style={{ height: 240 }} />
                : <div style={{ textAlign: 'center', padding: 60, color: '#999' }}>暂无数据</div>}
            </Card>
          </Col>
        </Row>

        {/* ── 明细表格 ── */}
        <Card
          title="菜品渠道毛利明细"
          size="small"
          extra={
            <Radio.Group
              value={labelFilter}
              onChange={e => setLabelFilter(e.target.value)}
              size="small"
            >
              <Radio.Button value="all">全部</Radio.Button>
              <Radio.Button value="赚钱">赚钱</Radio.Button>
              <Radio.Button value="勉强">勉强</Radio.Button>
              <Radio.Button value="亏钱">亏钱</Radio.Button>
            </Radio.Group>
          }
        >
          <Table
            dataSource={items}
            columns={columns}
            rowKey={r => `${r.dish_id}_${r.channel}`}
            size="small"
            pagination={{ pageSize: 20, showTotal: t => `共 ${t} 条` }}
            scroll={{ x: 900 }}
          />
        </Card>
      </Spin>
    </div>
  );
};

export default ChannelProfitPage;
