import React, { useState, useEffect, useCallback } from 'react';
import {
  Card, Row, Col, Select, DatePicker, Statistic, Table,
  Button, Typography, Space, Spin, Segmented,
} from 'antd';
import { BarChartOutlined, ReloadOutlined, FireOutlined } from '@ant-design/icons';
import ReactECharts from 'echarts-for-react';
import dayjs, { Dayjs } from 'dayjs';
import { apiClient } from '../services/api';
import { handleApiError } from '../utils/message';

const { Title } = Typography;
const { Option } = Select;
const { RangePicker } = DatePicker;

const OrderAnalyticsPage: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [stores, setStores] = useState<any[]>([]);
  const [storeId, setStoreId] = useState('STORE001');
  const [granularity, setGranularity] = useState<'hour' | 'day'>('hour');
  const [dateRange, setDateRange] = useState<[Dayjs, Dayjs]>([dayjs(), dayjs()]);
  const [trendData, setTrendData] = useState<any>(null);
  const [menuData, setMenuData] = useState<any>(null);

  const loadStores = useCallback(async () => {
    try {
      const res = await apiClient.get('/api/v1/stores');
      setStores(res.data?.stores || res.data || []);
    } catch { /* ignore */ }
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    const start = dateRange[0].format('YYYY-MM-DD');
    const end = dateRange[1].format('YYYY-MM-DD');
    try {
      const [trendRes, menuRes] = await Promise.all([
        apiClient.get('/api/v1/orders/trends', { params: { store_id: storeId, start_date: start, end_date: end, granularity } }),
        apiClient.get('/api/v1/orders/menu-performance', { params: { store_id: storeId, start_date: start, end_date: end, limit: 20 } }),
      ]);
      setTrendData(trendRes.data);
      setMenuData(menuRes.data);
    } catch (err: any) {
      handleApiError(err, '加载订单分析失败');
    } finally {
      setLoading(false);
    }
  }, [storeId, granularity, dateRange]);

  useEffect(() => { loadStores(); }, [loadStores]);
  useEffect(() => { load(); }, [load]);

  const trendPoints: any[] = trendData?.data || [];
  const menuItems: any[] = menuData?.top || [];

  const trendOption = {
    tooltip: { trigger: 'axis' },
    legend: { bottom: 0, data: ['订单数', '营收(元)'] },
    xAxis: { type: 'category', data: trendPoints.map((d: any) => d.time) },
    yAxis: [
      { type: 'value', name: '订单数' },
      { type: 'value', name: '营收(元)' },
    ],
    series: [
      {
        name: '订单数',
        type: 'bar',
        data: trendPoints.map((d: any) => d.orders),
        itemStyle: { color: '#1890ff' },
      },
      {
        name: '营收(元)',
        type: 'line',
        yAxisIndex: 1,
        data: trendPoints.map((d: any) => d.revenue.toFixed(0)),
        smooth: true,
        itemStyle: { color: '#52c41a' },
      },
    ],
  };

  const menuOption = {
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    xAxis: { type: 'value', name: '销量' },
    yAxis: { type: 'category', data: menuItems.slice(0, 10).map((d: any) => d.item_name).reverse(), axisLabel: { fontSize: 11 } },
    series: [{
      type: 'bar',
      data: menuItems.slice(0, 10).map((d: any) => d.quantity).reverse(),
      itemStyle: { color: '#fa8c16' },
      label: { show: true, position: 'right' },
    }],
  };

  const menuColumns = [
    { title: '排名', render: (_: any, __: any, i: number) => i + 1, width: 60 },
    { title: '菜品', dataIndex: 'item_name' },
    { title: '销量', dataIndex: 'quantity', sorter: (a: any, b: any) => a.quantity - b.quantity },
    { title: '营收(元)', dataIndex: 'revenue', render: (v: number) => v.toFixed(0), sorter: (a: any, b: any) => a.revenue - b.revenue },
    { title: '出现订单数', dataIndex: 'order_count' },
  ];

  const peakHour = trendData?.peak;
  const totalOrders = trendPoints.reduce((s: number, d: any) => s + d.orders, 0);
  const totalRevenue = trendPoints.reduce((s: number, d: any) => s + d.revenue, 0);

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <Title level={4} style={{ margin: 0 }}><BarChartOutlined /> 订单趋势分析</Title>
        <Space wrap>
          <Select value={storeId} onChange={setStoreId} style={{ width: 160 }}>
            {stores.length > 0
              ? stores.map((s: any) => <Option key={s.id || s.store_id} value={s.id || s.store_id}>{s.name}</Option>)
              : <Option value="STORE001">STORE001</Option>}
          </Select>
          <RangePicker
            value={dateRange}
            onChange={(v) => v && v[0] && v[1] && setDateRange([v[0], v[1]])}
            allowClear={false}
          />
          <Segmented
            options={[{ label: '按小时', value: 'hour' }, { label: '按天', value: 'day' }]}
            value={granularity}
            onChange={(v) => setGranularity(v as 'hour' | 'day')}
          />
          <Button icon={<ReloadOutlined />} onClick={load}>刷新</Button>
        </Space>
      </div>

      <Spin spinning={loading}>
        <Row gutter={16} style={{ marginBottom: 16 }}>
          <Col span={6}>
            <Card>
              <Statistic title="总订单数" value={totalOrders} suffix="单" />
            </Card>
          </Col>
          <Col span={6}>
            <Card>
              <Statistic title="总营收" value={totalRevenue.toFixed(0)} prefix="¥" />
            </Card>
          </Col>
          <Col span={6}>
            <Card>
              <Statistic
                title="高峰时段"
                value={peakHour || '--'}
                prefix={<FireOutlined style={{ color: '#ff4d4f' }} />}
              />
            </Card>
          </Col>
          <Col span={6}>
            <Card>
              <Statistic title="菜品种类" value={menuData?.total_items || 0} suffix="种" />
            </Card>
          </Col>
        </Row>

        <Row gutter={16} style={{ marginBottom: 16 }}>
          <Col span={14}>
            <Card title={`订单趋势（${granularity === 'hour' ? '按小时' : '按天'}）`}>
              <ReactECharts option={trendOption} style={{ height: 300 }} />
            </Card>
          </Col>
          <Col span={10}>
            <Card title="菜品销量 Top 10">
              <ReactECharts option={menuOption} style={{ height: 300 }} />
            </Card>
          </Col>
        </Row>

        <Card title="菜品销量明细">
          <Table
            dataSource={menuItems}
            columns={menuColumns}
            rowKey="item_name"
            size="middle"
            pagination={{ pageSize: 10 }}
          />
        </Card>
      </Spin>
    </div>
  );
};

export default OrderAnalyticsPage;
