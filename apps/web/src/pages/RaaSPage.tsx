import React, { useState, useCallback, useEffect } from 'react';
import { Card, Col, Row, Statistic, Select, Tabs, Descriptions, Tag, Progress, Alert } from 'antd';
import { apiClient } from '../services/api';
import { handleApiError } from '../utils/message';

const { Option } = Select;

const tierColor: Record<string, string> = { basic: 'default', growth: 'blue', premium: 'gold', enterprise: 'purple' };
const tierLabel: Record<string, string> = { basic: '基础版', growth: '成长版', premium: '高级版', enterprise: '企业版' };

const RaaSPage: React.FC = () => {
  const [storeId, setStoreId] = useState('STORE001');
  const [tier, setTier] = useState<any>(null);
  const [baseline, setBaseline] = useState<any>(null);
  const [effectMetrics, setEffectMetrics] = useState<any>(null);
  const [monthlyBill, setMonthlyBill] = useState<any>(null);
  const [valueProposition, setValueProposition] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [tierRes, baseRes, effectRes, billRes, valueRes] = await Promise.allSettled([
        apiClient.get(`/raas/pricing-tier/${storeId}`),
        apiClient.get(`/raas/baseline/${storeId}`),
        apiClient.get(`/raas/effect-metrics/${storeId}`),
        apiClient.get(`/raas/monthly-bill/${storeId}`),
        apiClient.get(`/raas/value-proposition/${storeId}`),
      ]);
      if (tierRes.status === 'fulfilled') setTier(tierRes.value.data);
      if (baseRes.status === 'fulfilled') setBaseline(baseRes.value.data);
      if (effectRes.status === 'fulfilled') setEffectMetrics(effectRes.value.data);
      if (billRes.status === 'fulfilled') setMonthlyBill(billRes.value.data);
      if (valueRes.status === 'fulfilled') setValueProposition(valueRes.value.data);
    } catch (err: any) {
      handleApiError(err, '加载RaaS数据失败');
    } finally {
      setLoading(false);
    }
  }, [storeId]);

  useEffect(() => { loadData(); }, [loadData]);

  const tabItems = [
    {
      key: 'overview',
      label: '定价概览',
      children: (
        <div>
          {tier && (
            <Alert
              message={<span>当前套餐：<Tag color={tierColor[tier.tier] || 'default'}>{tierLabel[tier.tier] || tier.tier}</Tag></span>}
              description={`月费：¥${(tier.monthly_fee || 0).toFixed(2)} | 效果分成比例：${((tier.revenue_share_rate || 0) * 100).toFixed(1)}%`}
              type="info"
              style={{ marginBottom: 16 }}
            />
          )}
          <Row gutter={16}>
            <Col span={6}><Card loading={loading}><Statistic title="基准营收" prefix="¥" value={(baseline?.avg_monthly_revenue || 0).toFixed(0)} /></Card></Col>
            <Col span={6}><Card loading={loading}><Statistic title="当月营收" prefix="¥" value={(effectMetrics?.current_revenue || 0).toFixed(0)} /></Card></Col>
            <Col span={6}><Card loading={loading}><Statistic title="营收增长" suffix="%" value={((effectMetrics?.revenue_growth || 0) * 100).toFixed(1)} valueStyle={{ color: (effectMetrics?.revenue_growth || 0) >= 0 ? '#52c41a' : '#ff4d4f' }} /></Card></Col>
            <Col span={6}><Card loading={loading}><Statistic title="本月账单" prefix="¥" value={(monthlyBill?.total_amount || 0).toFixed(2)} /></Card></Col>
          </Row>
        </div>
      ),
    },
    {
      key: 'bill',
      label: '账单明细',
      children: monthlyBill ? (
        <Card title="本月账单">
          <Descriptions bordered column={2}>
            <Descriptions.Item label="账单周期">{monthlyBill.billing_period || '-'}</Descriptions.Item>
            <Descriptions.Item label="套餐费用">¥{(monthlyBill.base_fee || 0).toFixed(2)}</Descriptions.Item>
            <Descriptions.Item label="效果分成">¥{(monthlyBill.performance_fee || 0).toFixed(2)}</Descriptions.Item>
            <Descriptions.Item label="总金额">¥{(monthlyBill.total_amount || 0).toFixed(2)}</Descriptions.Item>
            <Descriptions.Item label="支付状态"><Tag color={monthlyBill.paid ? 'green' : 'orange'}>{monthlyBill.paid ? '已支付' : '待支付'}</Tag></Descriptions.Item>
          </Descriptions>
        </Card>
      ) : <Card loading={loading} />,
    },
    {
      key: 'value',
      label: '价值主张',
      children: valueProposition ? (
        <Card title="AI带来的价值">
          <Row gutter={16}>
            <Col span={8}><Statistic title="节省人工成本" prefix="¥" value={(valueProposition.labor_savings || 0).toFixed(0)} /></Col>
            <Col span={8}><Statistic title="减少食材浪费" prefix="¥" value={(valueProposition.waste_reduction || 0).toFixed(0)} /></Col>
            <Col span={8}><Statistic title="营收提升" prefix="¥" value={(valueProposition.revenue_increase || 0).toFixed(0)} /></Col>
          </Row>
          <div style={{ marginTop: 16 }}>
            <div style={{ marginBottom: 8 }}>ROI</div>
            <Progress percent={Math.min((valueProposition.roi || 0) * 100, 100)} format={() => `${((valueProposition.roi || 0) * 100).toFixed(0)}%`} />
          </div>
        </Card>
      ) : <Card loading={loading} />,
    },
  ];

  return (
    <div>
      <div style={{ marginBottom: 16 }}>
        <Select value={storeId} onChange={setStoreId} style={{ width: 160 }}>
          <Option value="STORE001">门店001</Option>
          <Option value="STORE002">门店002</Option>
        </Select>
      </div>
      <Tabs items={tabItems} />
    </div>
  );
};

export default RaaSPage;
