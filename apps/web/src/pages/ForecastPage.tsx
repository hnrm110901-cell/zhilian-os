import React, { useState, useCallback, useEffect } from 'react';
import { Card, Col, Row, Select, InputNumber, Button, Tabs, Statistic, Space, Spin } from 'antd';
import { ReloadOutlined, DeleteOutlined } from '@ant-design/icons';
import ReactECharts from 'echarts-for-react';
import { apiClient } from '../services/api';
import { handleApiError, showSuccess, showLoading } from '../utils/message';

const { Option } = Select;

const ForecastPage: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [stores, setStores] = useState<any[]>([]);
  const [selectedStore, setSelectedStore] = useState('STORE001');
  const [metric, setMetric] = useState('revenue');
  const [horizonDays, setHorizonDays] = useState(7);
  const [forecastData, setForecastData] = useState<any>(null);

  const loadStores = useCallback(async () => {
    try {
      const res = await apiClient.get('/stores');
      setStores(res.data?.stores || res.data || []);
    } catch (err: any) {
      handleApiError(err, '加载门店列表失败');
    }
  }, []);

  const loadForecast = useCallback(async () => {
    setLoading(true);
    try {
      const res = await apiClient.get(`/forecast/prophet/${selectedStore}`, {
        params: { horizon_days: horizonDays, metric },
      });
      setForecastData(res.data);
    } catch (err: any) {
      handleApiError(err, '加载预测数据失败');
    } finally {
      setLoading(false);
    }
  }, [selectedStore, metric, horizonDays]);

  useEffect(() => {
    loadStores();
  }, [loadStores]);

  useEffect(() => {
    loadForecast();
  }, [loadForecast]);

  const clearCache = async () => {
    const hide = showLoading('清除缓存中...');
    try {
      await apiClient.delete(`/forecast/prophet/${selectedStore}/cache`, {
        params: { metric },
      });
      showSuccess('缓存已清除');
      loadForecast();
    } catch (err: any) {
      handleApiError(err, '清除缓存失败');
    } finally {
      hide();
    }
  };

  const buildChartOption = (metricKey: string, title: string) => {
    const history = forecastData?.history?.[metricKey] || [];
    const forecast = forecastData?.forecast?.[metricKey] || [];
    return {
      title: { text: title, left: 'center' },
      tooltip: { trigger: 'axis' },
      legend: { data: ['历史', '预测'], bottom: 0 },
      xAxis: { type: 'category', data: [...history.map((d: any) => d.date), ...forecast.map((d: any) => d.date)] },
      yAxis: { type: 'value' },
      series: [
        { name: '历史', type: 'line', data: history.map((d: any) => d.value), itemStyle: { color: '#1890ff' } },
        { name: '预测', type: 'line', data: [...Array(history.length).fill(null), ...forecast.map((d: any) => d.value)], itemStyle: { color: '#f5222d' }, lineStyle: { type: 'dashed' } },
      ],
    };
  };

  const tabItems = [
    { key: 'revenue', label: '营收预测', children: <ReactECharts option={buildChartOption('revenue', '营收预测')} style={{ height: 360 }} /> },
    { key: 'traffic', label: '客流预测', children: <ReactECharts option={buildChartOption('traffic', '客流预测')} style={{ height: 360 }} /> },
    { key: 'orders', label: '订单预测', children: <ReactECharts option={buildChartOption('orders', '订单预测')} style={{ height: 360 }} /> },
  ];

  return (
    <div>
      <Space wrap style={{ marginBottom: 16 }}>
        <Select value={selectedStore} onChange={setSelectedStore} style={{ width: 160 }} placeholder="选择门店">
          {stores.length > 0 ? stores.map((s: any) => (
            <Option key={s.store_id || s.id} value={s.store_id || s.id}>{s.name || s.store_id || s.id}</Option>
          )) : <Option value="STORE001">STORE001</Option>}
        </Select>
        <Select value={metric} onChange={setMetric} style={{ width: 120 }}>
          <Option value="revenue">营收</Option>
          <Option value="traffic">客流</Option>
          <Option value="orders">订单</Option>
        </Select>
        <InputNumber min={1} max={90} value={horizonDays} onChange={(v) => setHorizonDays(v || 7)} addonAfter="天" style={{ width: 120 }} />
        <Button icon={<ReloadOutlined />} onClick={loadForecast}>刷新</Button>
        <Button icon={<DeleteOutlined />} onClick={clearCache} danger>清除缓存</Button>
      </Space>

      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={12}>
          <Card><Statistic title="预测总营收" value={forecastData?.summary?.total_revenue ?? '--'} prefix="¥" /></Card>
        </Col>
        <Col span={12}>
          <Card><Statistic title="预测总订单数" value={forecastData?.summary?.total_orders ?? '--'} /></Card>
        </Col>
      </Row>

      <Card>
        <Spin spinning={loading}>
          <Tabs items={tabItems} />
        </Spin>
      </Card>
    </div>
  );
};

export default ForecastPage;
