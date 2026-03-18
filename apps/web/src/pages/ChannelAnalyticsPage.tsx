/**
 * 渠道分析仪表板 — Phase P1 (易订PRO能力)
 * 渠道来源统计 · 转化率分析 · 退订率管理
 */
import React, { useEffect, useState } from 'react';
import {
  Card, Row, Col, Table, Statistic, DatePicker, Select, Spin, Alert,
  Typography, Tag, Progress, Space,
} from 'antd';
import {
  FunnelPlotOutlined, ShareAltOutlined, CloseCircleOutlined,
  RiseOutlined, FallOutlined,
} from '@ant-design/icons';
import { apiClient } from '../services/api';
import dayjs from 'dayjs';

const { Title, Text } = Typography;
const { RangePicker } = DatePicker;

interface ChannelStat {
  channel: string;
  count: number;
  percentage: number;
  total_commission: number;
}

interface ChannelConversion {
  channel: string;
  total: number;
  completed: number;
  conversion_rate: number;
}

interface CancellationData {
  total_reservations: number;
  cancelled: number;
  no_show: number;
  cancellation_rate: number;
  no_show_rate: number;
  effective_rate: number;
}

const CHANNEL_LABELS: Record<string, string> = {
  meituan: '美团',
  dianping: '大众点评',
  douyin: '抖音',
  xiaohongshu: '小红书',
  wechat: '微信/企微',
  phone: '电话',
  walk_in: '到店',
  referral: '老客推荐',
  yiding: '易订',
  mini_program: '小程序',
  other: '其他',
};

const CHANNEL_COLORS: Record<string, string> = {
  meituan: 'gold',
  dianping: 'orange',
  douyin: 'magenta',
  wechat: 'green',
  phone: 'blue',
  walk_in: 'cyan',
  referral: 'purple',
  yiding: 'geekblue',
};

export default function ChannelAnalyticsPage() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [storeId] = useState(localStorage.getItem('store_id') || '');
  const [dateRange, setDateRange] = useState<[dayjs.Dayjs, dayjs.Dayjs]>([
    dayjs().subtract(30, 'day'),
    dayjs(),
  ]);

  const [channelStats, setChannelStats] = useState<{ total_reservations: number; channels: ChannelStat[] } | null>(null);
  const [conversions, setConversions] = useState<ChannelConversion[]>([]);
  const [cancellation, setCancellation] = useState<CancellationData | null>(null);

  const fetchData = async () => {
    setLoading(true);
    setError(null);
    const [start, end] = dateRange;
    const params = `store_id=${storeId}&start_date=${start.format('YYYY-MM-DD')}&end_date=${end.format('YYYY-MM-DD')}`;
    try {
      const [stats, conv, cancel] = await Promise.all([
        apiClient.get<any>(`/api/v1/channel-analytics/stats?${params}`),
        apiClient.get<ChannelConversion[]>(`/api/v1/channel-analytics/conversion?${params}`),
        apiClient.get<CancellationData>(`/api/v1/channel-analytics/cancellation?${params}`),
      ]);
      setChannelStats(stats);
      setConversions(conv);
      setCancellation(cancel);
    } catch (e: any) {
      setError(e?.message ?? '加载失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, [dateRange]);

  const channelColumns = [
    {
      title: '渠道',
      dataIndex: 'channel',
      key: 'channel',
      render: (v: string) => (
        <Tag color={CHANNEL_COLORS[v] || 'default'}>
          {CHANNEL_LABELS[v] || v}
        </Tag>
      ),
    },
    { title: '预订量', dataIndex: 'count', key: 'count', sorter: (a: ChannelStat, b: ChannelStat) => a.count - b.count },
    {
      title: '占比',
      dataIndex: 'percentage',
      key: 'percentage',
      render: (v: number) => <Progress percent={v} size="small" style={{ width: 120 }} />,
    },
    {
      title: '佣金成本',
      dataIndex: 'total_commission',
      key: 'commission',
      render: (v: number) => v > 0 ? <Text type="danger">¥{v.toFixed(2)}</Text> : '-',
    },
  ];

  const conversionColumns = [
    {
      title: '渠道',
      dataIndex: 'channel',
      key: 'channel',
      render: (v: string) => <Tag color={CHANNEL_COLORS[v] || 'default'}>{CHANNEL_LABELS[v] || v}</Tag>,
    },
    { title: '总预订', dataIndex: 'total', key: 'total' },
    { title: '完成', dataIndex: 'completed', key: 'completed' },
    {
      title: '转化率',
      dataIndex: 'conversion_rate',
      key: 'rate',
      render: (v: number) => (
        <Text style={{ color: v >= 70 ? '#52c41a' : v >= 40 ? '#faad14' : '#ff4d4f' }}>
          {v}%
        </Text>
      ),
      sorter: (a: ChannelConversion, b: ChannelConversion) => a.conversion_rate - b.conversion_rate,
    },
  ];

  if (error) return <Alert type="error" message={error} />;

  return (
    <div style={{ maxWidth: 1200, margin: '0 auto' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <Title level={3} style={{ margin: 0 }}>
          <ShareAltOutlined /> 渠道分析
        </Title>
        <RangePicker
          value={dateRange}
          onChange={(dates) => dates && setDateRange(dates as [dayjs.Dayjs, dayjs.Dayjs])}
        />
      </div>

      <Spin spinning={loading}>
        {/* 顶部统计卡片 */}
        <Row gutter={16} style={{ marginBottom: 16 }}>
          <Col span={6}>
            <Card size="small">
              <Statistic
                title="总预订"
                value={channelStats?.total_reservations || 0}
                suffix="单"
              />
            </Card>
          </Col>
          <Col span={6}>
            <Card size="small">
              <Statistic
                title="有效率"
                value={cancellation?.effective_rate || 0}
                suffix="%"
                valueStyle={{ color: (cancellation?.effective_rate || 0) >= 80 ? '#3f8600' : '#cf1322' }}
                prefix={<RiseOutlined />}
              />
            </Card>
          </Col>
          <Col span={6}>
            <Card size="small">
              <Statistic
                title="退订率"
                value={cancellation?.cancellation_rate || 0}
                suffix="%"
                valueStyle={{ color: (cancellation?.cancellation_rate || 0) <= 10 ? '#3f8600' : '#cf1322' }}
                prefix={<CloseCircleOutlined />}
              />
            </Card>
          </Col>
          <Col span={6}>
            <Card size="small">
              <Statistic
                title="爽约率"
                value={cancellation?.no_show_rate || 0}
                suffix="%"
                valueStyle={{ color: (cancellation?.no_show_rate || 0) <= 5 ? '#3f8600' : '#cf1322' }}
                prefix={<FallOutlined />}
              />
            </Card>
          </Col>
        </Row>

        {/* 渠道统计表 */}
        <Row gutter={16}>
          <Col span={12}>
            <Card title="渠道来源分布" size="small">
              <Table
                dataSource={channelStats?.channels || []}
                columns={channelColumns}
                rowKey="channel"
                pagination={false}
                size="small"
              />
            </Card>
          </Col>
          <Col span={12}>
            <Card title="渠道转化率" size="small">
              <Table
                dataSource={conversions}
                columns={conversionColumns}
                rowKey="channel"
                pagination={false}
                size="small"
              />
            </Card>
          </Col>
        </Row>
      </Spin>
    </div>
  );
}
