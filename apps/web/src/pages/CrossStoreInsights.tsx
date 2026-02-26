import React, { useState, useCallback, useEffect } from 'react';
import { Card, Col, Row, Select, DatePicker, Tabs, Statistic, Table, Alert, Tag, Space } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import ReactECharts from 'echarts-for-react';
import dayjs from 'dayjs';
import { apiClient } from '../services/api';
import { handleApiError } from '../utils/message';

const { Option } = Select;

const CrossStoreInsights: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [metric, setMetric] = useState('revenue');
  const [targetDate, setTargetDate] = useState(dayjs().format('YYYY-MM-DD'));
  const [period, setPeriod] = useState('week');
  const [anomalies, setAnomalies] = useState<any>(null);
  const [bestPractices, setBestPractices] = useState<any>(null);
  const [periodComparison, setPeriodComparison] = useState<any>(null);
  const [summary, setSummary] = useState<any>(null);

  const loadAll = useCallback(async () => {
    setLoading(true);
    try {
      const [a, b, c, s] = await Promise.allSettled([
        apiClient.get('/api/v1/insights/anomalies', { params: { metric, target_date: targetDate, threshold: 2.0 } }),
        apiClient.get('/api/v1/insights/best-practices', { params: { metric, top_n: 3 } }),
        apiClient.get('/api/v1/insights/period-comparison', { params: { metric, period } }),
        apiClient.get('/api/v1/insights/summary', { params: { metric } }),
      ]);
      if (a.status === 'fulfilled') setAnomalies(a.value.data);
      if (b.status === 'fulfilled') setBestPractices(b.value.data);
      if (c.status === 'fulfilled') setPeriodComparison(c.value.data);
      if (s.status === 'fulfilled') setSummary(s.value.data);
    } catch (err: any) {
      handleApiError(err, '加载跨门店洞察失败');
    } finally {
      setLoading(false);
    }
  }, [metric, targetDate, period]);

  useEffect(() => { loadAll(); }, [loadAll]);

  const anomalyColumns: ColumnsType<any> = [
    { title: '门店', dataIndex: 'store_id', key: 'store_id' },
    { title: '指标值', dataIndex: 'value', key: 'value', render: (v: number) => v?.toFixed(2) },
    { title: '偏差', dataIndex: 'deviation', key: 'deviation', render: (v: number) => v?.toFixed(2) },
    { title: '状态', dataIndex: 'status', key: 'status', render: (s: string) => <Tag color={s === 'anomaly' ? 'red' : 'green'}>{s === 'anomaly' ? '异常' : '正常'}</Tag> },
  ];

  const topStores = bestPractices?.top_stores || [];
  const bottomStores = bestPractices?.bottom_stores || [];
  const barOption = {
    tooltip: { trigger: 'axis' },
    legend: { data: ['最佳门店', '最差门店'], bottom: 0 },
    xAxis: { type: 'category', data: topStores.map((s: any) => s.store_id) },
    yAxis: { type: 'value' },
    series: [
      { name: '最佳门店', type: 'bar', data: topStores.map((s: any) => s.value), itemStyle: { color: '#52c41a' } },
      { name: '最差门店', type: 'bar', data: bottomStores.map((s: any) => s.value), itemStyle: { color: '#f5222d' } },
    ],
  };

  const compStores = periodComparison?.stores || [];
  const growthOption = {
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'category', data: compStores.map((s: any) => s.store_id) },
    yAxis: { type: 'value', axisLabel: { formatter: '{value}%' } },
    series: [{
      type: 'bar',
      data: compStores.map((s: any) => ({
        value: s.growth_rate,
        itemStyle: { color: s.growth_rate >= 0 ? '#52c41a' : '#f5222d' },
      })),
    }],
  };

  const anomalyCount = anomalies?.anomalies?.length ?? 0;
  const bestStore = topStores[0]?.store_id ?? '--';
  const worstStore = bottomStores[bottomStores.length - 1]?.store_id ?? '--';
  const gap = topStores.length && bottomStores.length
    ? ((topStores[0]?.value ?? 0) - (bottomStores[bottomStores.length - 1]?.value ?? 0)).toFixed(0)
    : '--';

  const tabItems = [
    {
      key: 'summary', label: '综合摘要',
      children: (
        <div>
          {summary?.text && <Alert message={summary.text} type="info" showIcon style={{ marginBottom: 16 }} />}
          <Row gutter={16}>
            {(summary?.metrics || []).map((m: any, i: number) => (
              <Col span={6} key={i}><Card><Statistic title={m.label} value={m.value} /></Card></Col>
            ))}
          </Row>
        </div>
      ),
    },
    {
      key: 'anomalies', label: '异常检测',
      children: <Table columns={anomalyColumns} dataSource={anomalies?.anomalies || []} rowKey="store_id" loading={loading} />,
    },
    {
      key: 'best-practices', label: '最佳实践',
      children: <ReactECharts option={barOption} style={{ height: 360 }} />,
    },
    {
      key: 'period-comparison', label: '周期对比',
      children: <ReactECharts option={growthOption} style={{ height: 360 }} />,
    },
  ];

  return (
    <div>
      <Space wrap style={{ marginBottom: 16 }}>
        <Select value={metric} onChange={setMetric} style={{ width: 120 }}>
          <Option value="revenue">营收</Option>
          <Option value="orders">订单</Option>
        </Select>
        <DatePicker defaultValue={dayjs()} onChange={(_, ds) => setTargetDate(ds as string)} />
        <Select value={period} onChange={setPeriod} style={{ width: 100 }}>
          <Option value="week">周</Option>
          <Option value="month">月</Option>
        </Select>
      </Space>

      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={6}><Card><Statistic title="异常门店数" value={anomalyCount} /></Card></Col>
        <Col span={6}><Card><Statistic title="最佳门店" value={bestStore} /></Card></Col>
        <Col span={6}><Card><Statistic title="最差门店" value={worstStore} /></Card></Col>
        <Col span={6}><Card><Statistic title="绩效差距" value={gap} /></Card></Col>
      </Row>

      <Card><Tabs items={tabItems} /></Card>
    </div>
  );
};

export default CrossStoreInsights;
