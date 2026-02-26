import React, { useState, useCallback, useEffect } from 'react';
import { Card, Col, Row, Select, Form, InputNumber, Button, Tabs, Statistic, Table, DatePicker, Input, Space } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { apiClient } from '../services/api';
import { handleApiError } from '../utils/message';

const { Option } = Select;
const { RangePicker } = DatePicker;

const RecommendationsPage: React.FC = () => {
  const [stores, setStores] = useState<any[]>([]);
  const [selectedStore, setSelectedStore] = useState('STORE001');
  const [dishResult, setDishResult] = useState<any[]>([]);
  const [pricingResult, setPricingResult] = useState<any>(null);
  const [campaignResult, setCampaignResult] = useState<any>(null);
  const [perfResult, setPerfResult] = useState<any>(null);
  const [loadingDish, setLoadingDish] = useState(false);
  const [loadingPrice, setLoadingPrice] = useState(false);
  const [loadingCampaign, setLoadingCampaign] = useState(false);
  const [loadingPerf, setLoadingPerf] = useState(false);

  const loadStores = useCallback(async () => {
    try {
      const res = await apiClient.get('/api/v1/stores');
      setStores(res.data?.stores || res.data || []);
    } catch (err: any) {
      handleApiError(err, '加载门店列表失败');
    }
  }, []);

  useEffect(() => { loadStores(); }, [loadStores]);

  const submitDish = async (values: any) => {
    setLoadingDish(true);
    try {
      const res = await apiClient.post('/api/v1/recommendations/dishes', { ...values, store_id: selectedStore });
      setDishResult(res.data?.recommendations || res.data || []);
    } catch (err: any) {
      handleApiError(err, '获取菜品推荐失败');
    } finally {
      setLoadingDish(false);
    }
  };

  const submitPricing = async (values: any) => {
    setLoadingPrice(true);
    try {
      const res = await apiClient.post('/api/v1/recommendations/pricing/optimize', { ...values, store_id: selectedStore });
      setPricingResult(res.data);
    } catch (err: any) {
      handleApiError(err, '获取定价建议失败');
    } finally {
      setLoadingPrice(false);
    }
  };

  const submitCampaign = async (values: any) => {
    setLoadingCampaign(true);
    try {
      const res = await apiClient.post('/api/v1/recommendations/marketing/campaign', { ...values, store_id: selectedStore });
      setCampaignResult(res.data);
    } catch (err: any) {
      handleApiError(err, '获取营销方案失败');
    } finally {
      setLoadingCampaign(false);
    }
  };

  const submitPerf = async (values: any) => {
    setLoadingPerf(true);
    try {
      const [start, end] = values.date_range || [];
      const res = await apiClient.post('/api/v1/recommendations/performance', {
        store_id: selectedStore,
        start_date: start?.format('YYYY-MM-DD'),
        end_date: end?.format('YYYY-MM-DD'),
      });
      setPerfResult(res.data);
    } catch (err: any) {
      handleApiError(err, '获取推荐效果失败');
    } finally {
      setLoadingPerf(false);
    }
  };

  const dishColumns: ColumnsType<any> = [
    { title: '菜品', dataIndex: 'dish_name', key: 'dish_name' },
    { title: '评分', dataIndex: 'score', key: 'score', render: (v: number) => v?.toFixed(2) },
    { title: '原因', dataIndex: 'reason', key: 'reason', ellipsis: true },
    { title: '价格', dataIndex: 'price', key: 'price', render: (v: number) => `¥${v}` },
    { title: '利润', dataIndex: 'profit', key: 'profit', render: (v: number) => `¥${v}` },
    { title: '置信度', dataIndex: 'confidence', key: 'confidence', render: (v: number) => `${((v || 0) * 100).toFixed(0)}%` },
  ];

  const tabItems = [
    {
      key: 'dish', label: '菜品推荐',
      children: (
        <div>
          <Form layout="inline" onFinish={submitDish} style={{ marginBottom: 16 }}>
            <Form.Item name="customer_id" label="顾客ID"><Input placeholder="顾客ID" /></Form.Item>
            <Form.Item name="top_k" label="推荐数量" initialValue={5}><InputNumber min={1} max={20} /></Form.Item>
            <Form.Item><Button type="primary" htmlType="submit" loading={loadingDish}>获取推荐</Button></Form.Item>
          </Form>
          <Table columns={dishColumns} dataSource={dishResult} rowKey={(r, i) => `${r.dish_name}-${i}`} />
        </div>
      ),
    },
    {
      key: 'pricing', label: '动态定价',
      children: (
        <div>
          <Form layout="inline" onFinish={submitPricing} style={{ marginBottom: 16 }}>
            <Form.Item name="dish_id" label="菜品ID" rules={[{ required: true }]}><Input placeholder="菜品ID" /></Form.Item>
            <Form.Item><Button type="primary" htmlType="submit" loading={loadingPrice}>获取定价</Button></Form.Item>
          </Form>
          {pricingResult && (
            <Row gutter={16}>
              <Col span={6}><Card><Statistic title="当前价格" value={pricingResult.current_price} prefix="¥" /></Card></Col>
              <Col span={6}><Card><Statistic title="推荐价格" value={pricingResult.recommended_price} prefix="¥" /></Card></Col>
              <Col span={6}><Card><Statistic title="变化率" value={pricingResult.change_rate} suffix="%" /></Card></Col>
              <Col span={6}><Card><Statistic title="预期收益" value={pricingResult.expected_revenue} prefix="¥" /></Card></Col>
            </Row>
          )}
          {pricingResult?.strategy && <Card style={{ marginTop: 16 }} title="策略说明"><p>{pricingResult.strategy}</p><p>{pricingResult.reason}</p></Card>}
        </div>
      ),
    },
    {
      key: 'campaign', label: '营销活动',
      children: (
        <div>
          <Form layout="inline" onFinish={submitCampaign} style={{ marginBottom: 16 }}>
            <Form.Item name="objective" label="目标"><Input placeholder="如：提升客流" /></Form.Item>
            <Form.Item name="budget" label="预算"><InputNumber min={0} placeholder="预算" /></Form.Item>
            <Form.Item name="target_audience" label="目标客群"><Input placeholder="目标客群" /></Form.Item>
            <Form.Item><Button type="primary" htmlType="submit" loading={loadingCampaign}>生成方案</Button></Form.Item>
          </Form>
          {campaignResult && (
            <Card title="营销方案">
              <p><b>活动名称：</b>{campaignResult.campaign_name}</p>
              <p><b>活动描述：</b>{campaignResult.description}</p>
              <p><b>预期效果：</b>{campaignResult.expected_outcome}</p>
            </Card>
          )}
        </div>
      ),
    },
    {
      key: 'performance', label: '推荐效果',
      children: (
        <div>
          <Form layout="inline" onFinish={submitPerf} style={{ marginBottom: 16 }}>
            <Form.Item name="date_range" label="日期范围"><RangePicker /></Form.Item>
            <Form.Item><Button type="primary" htmlType="submit" loading={loadingPerf}>查询效果</Button></Form.Item>
          </Form>
          {perfResult && (
            <Row gutter={16}>
              <Col span={8}><Card><Statistic title="接受率" value={((perfResult.acceptance_rate || 0) * 100).toFixed(1)} suffix="%" /></Card></Col>
              <Col span={8}><Card><Statistic title="营收影响" value={perfResult.revenue_impact} prefix="¥" /></Card></Col>
              <Col span={8}><Card><Statistic title="满意度" value={((perfResult.satisfaction_score || 0) * 100).toFixed(1)} suffix="%" /></Card></Col>
            </Row>
          )}
        </div>
      ),
    },
  ];

  return (
    <div>
      <Space style={{ marginBottom: 16 }}>
        <span>门店：</span>
        <Select value={selectedStore} onChange={setSelectedStore} style={{ width: 160 }}>
          {stores.length > 0 ? stores.map((s: any) => (
            <Option key={s.store_id || s.id} value={s.store_id || s.id}>{s.name || s.store_id || s.id}</Option>
          )) : <Option value="STORE001">STORE001</Option>}
        </Select>
      </Space>
      <Card><Tabs items={tabItems} /></Card>
    </div>
  );
};

export default RecommendationsPage;
