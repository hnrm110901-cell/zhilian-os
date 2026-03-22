import React, { useState, useEffect, useCallback } from 'react';
import {
  Card, Row, Col, Select, Statistic, Table, Tag, Button,
  Typography, Space, Spin, Progress,
} from 'antd';
import { DollarOutlined, ReloadOutlined } from '@ant-design/icons';
import ReactECharts from 'echarts-for-react';
import { apiClient } from '../services/api';
import { handleApiError } from '../utils/message';

const { Title, Text } = Typography;
const { Option } = Select;

const DishCostPage: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [stores, setStores] = useState<any[]>([]);
  const [storeId, setStoreId] = useState(localStorage.getItem('store_id') || '');
  const [data, setData] = useState<any>(null);

  const loadStores = useCallback(async () => {
    try {
      const res = await apiClient.get('/api/v1/stores');
      setStores(res.stores || res || []);
    } catch { /* ignore */ }
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await apiClient.get('/api/v1/dishes/cost-analysis', {
        params: { store_id: storeId, limit: 50 },
      });
      setData(res);
    } catch (err: any) {
      handleApiError(err, '加载成本分析失败');
    } finally {
      setLoading(false);
    }
  }, [storeId]);

  useEffect(() => { loadStores(); }, [loadStores]);
  useEffect(() => { load(); }, [load]);

  const items: any[] = data?.items || [];
  const topProfit: any[] = data?.top_profit || [];
  const lowProfit: any[] = data?.low_profit || [];

  // 利润率分布柱状图
  const barOption = {
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'category', data: items.slice(0, 15).map((d: any) => d.name), axisLabel: { rotate: 30, fontSize: 11 } },
    yAxis: { type: 'value', name: '利润率 (%)' },
    series: [{
      type: 'bar',
      data: items.slice(0, 15).map((d: any) => ({
        value: d.profit_margin,
        itemStyle: { color: d.profit_margin >= 60 ? '#1A7A52' : d.profit_margin >= 40 ? '#FF6B2C' : '#C53030' },
      })),
    }],
  };

  const columns = [
    { title: '菜品', dataIndex: 'name' },
    { title: '售价', dataIndex: 'price', render: (v: number) => `¥${v.toFixed(2)}` },
    { title: '成本', dataIndex: 'cost', render: (v: number) => `¥${v.toFixed(2)}` },
    {
      title: '利润率',
      dataIndex: 'profit_margin',
      render: (v: number) => (
        <Progress
          percent={v}
          size="small"
          status={v >= 60 ? 'success' : v >= 40 ? 'normal' : 'exception'}
          format={(p) => `${p}%`}
        />
      ),
      sorter: (a: any, b: any) => a.profit_margin - b.profit_margin,
    },
    { title: '总销量', dataIndex: 'total_sales' },
    { title: '总营收', dataIndex: 'total_revenue', render: (v: number) => `¥${v.toFixed(0)}` },
  ];

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <Title level={4} style={{ margin: 0 }}><DollarOutlined /> 菜品成本分析</Title>
        <Space>
          <Select value={storeId} onChange={setStoreId} style={{ width: 160 }}>
            {stores.length > 0
              ? stores.map((s: any) => <Option key={s.id || s.store_id} value={s.id || s.store_id}>{s.name}</Option>)
            : null}
          </Select>
          <Button icon={<ReloadOutlined />} onClick={load}>刷新</Button>
        </Space>
      </div>

      <Spin spinning={loading}>
        <Row gutter={16} style={{ marginBottom: 16 }}>
          <Col span={6}>
            <Card>
              <Statistic title="分析菜品数" value={data?.total || 0} suffix="道" />
            </Card>
          </Col>
          <Col span={6}>
            <Card>
              <Statistic
                title="平均利润率"
                value={data?.overall_avg_margin || 0}
                suffix="%"
                valueStyle={{ color: (data?.overall_avg_margin || 0) >= 50 ? '#1A7A52' : '#faad14' }}
              />
            </Card>
          </Col>
          <Col span={6}>
            <Card>
              <Statistic
                title="最高利润率"
                value={topProfit[0]?.profit_margin || 0}
                suffix="%"
                valueStyle={{ color: '#1A7A52' }}
              />
              {topProfit[0] && <Text type="secondary" style={{ fontSize: 12 }}>{topProfit[0].name}</Text>}
            </Card>
          </Col>
          <Col span={6}>
            <Card>
              <Statistic
                title="最低利润率"
                value={lowProfit[0]?.profit_margin || 0}
                suffix="%"
                valueStyle={{ color: '#C53030' }}
              />
              {lowProfit[0] && <Text type="secondary" style={{ fontSize: 12 }}>{lowProfit[0].name}</Text>}
            </Card>
          </Col>
        </Row>

        <Card title="利润率分布 (Top 15)" style={{ marginBottom: 16 }}>
          {items.length > 0
            ? <ReactECharts option={barOption} style={{ height: 280 }} />
            : <Text type="secondary">暂无数据</Text>}
        </Card>

        <Row gutter={16} style={{ marginBottom: 16 }}>
          <Col span={12}>
            <Card title="🏆 高利润菜品 Top 5" size="small">
              {topProfit.map((d: any, i: number) => (
                <div key={d.dish_id} style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0', borderBottom: '1px solid #f0f0f0' }}>
                  <Text>{i + 1}. {d.name}</Text>
                  <Tag color="green">{d.profit_margin}%</Tag>
                </div>
              ))}
            </Card>
          </Col>
          <Col span={12}>
            <Card title="⚠️ 低利润菜品 Top 5" size="small">
              {lowProfit.map((d: any, i: number) => (
                <div key={d.dish_id} style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0', borderBottom: '1px solid #f0f0f0' }}>
                  <Text>{i + 1}. {d.name}</Text>
                  <Tag color="red">{d.profit_margin}%</Tag>
                </div>
              ))}
            </Card>
          </Col>
        </Row>

        <Card title="全部菜品成本明细">
          <Table
            dataSource={items}
            columns={columns}
            rowKey="dish_id"
            size="middle"
            pagination={{ pageSize: 15 }}
          />
        </Card>
      </Spin>
    </div>
  );
};

export default DishCostPage;
