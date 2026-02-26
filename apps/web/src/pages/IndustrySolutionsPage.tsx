import React, { useState, useCallback, useEffect } from 'react';
import {
  Card, Row, Col, Statistic, Space, Button,
  Select, Spin, Typography, Alert
} from 'antd';
import { GlobalOutlined, CheckCircleOutlined, AppstoreAddOutlined } from '@ant-design/icons';
import { apiClient } from '../services/api';
import { handleApiError, showSuccess } from '../utils/message';

const { Title } = Typography;
const { Option } = Select;

interface Solution {
  solution_id: string;
  industry_type: string;
  name: string;
  description: string;
  templates_count: number;
  best_practices_count: number;
  kpi_benchmarks: Record<string, number>;
}

const industryLabel: Record<string, string> = {
  chinese_restaurant: '中餐连锁',
  fast_food: '快餐',
  cafe: '咖啡厅',
  hotpot: '火锅',
  buffet: '自助餐',
};

const IndustrySolutionsPage: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [solution, setSolution] = useState<Solution | null>(null);
  const [applyResult, setApplyResult] = useState<Record<string, unknown> | null>(null);
  const [industryType, setIndustryType] = useState('chinese_restaurant');
  const [storeId, setStoreId] = useState('STORE001');
  const [stores, setStores] = useState<any[]>([]);

  const loadStores = useCallback(async () => {
    try {
      const res = await apiClient.get('/stores');
      setStores(res.data?.stores || res.data || []);
    } catch { /* ignore */ }
  }, []);

  useEffect(() => { loadStores(); }, [loadStores]);

  const handleGetSolution = async () => {
    setLoading(true);
    try {
      const res = await apiClient.get(`/api/v1/industry/solution/${industryType}`);
      setSolution(res.data.solution);
    } catch (err) { handleApiError(err); }
    finally { setLoading(false); }
  };

  const handleApply = async () => {
    setLoading(true);
    try {
      const res = await apiClient.post('/api/v1/industry/apply', { store_id: storeId, industry_type: industryType });
      setApplyResult(res.data);
      showSuccess('行业解决方案已应用');
    } catch (err) { handleApiError(err); }
    finally { setLoading(false); }
  };

  return (
    <Spin spinning={loading}>
      <Space direction="vertical" size="large" style={{ width: '100%' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <Title level={4} style={{ margin: 0 }}>行业解决方案</Title>
          <Space>
            <Select value={storeId} onChange={setStoreId} style={{ width: 140 }}>
              {stores.length > 0 ? stores.map((s: any) => (
                <Option key={s.store_id || s.id} value={s.store_id || s.id}>{s.name || s.store_id || s.id}</Option>
              )) : <Option value="STORE001">门店 001</Option>}
            </Select>
            <Select value={industryType} onChange={setIndustryType} style={{ width: 160 }}>
              {Object.entries(industryLabel).map(([k, v]) => (
                <Option key={k} value={k}>{v}</Option>
              ))}
            </Select>
            <Button type="primary" icon={<GlobalOutlined />} onClick={handleGetSolution}>查询方案</Button>
          </Space>
        </div>

        {solution && (
          <>
            <Row gutter={16}>
              <Col span={8}>
                <Card><Statistic title="模板数量" value={solution.templates_count} prefix={<AppstoreAddOutlined />} /></Card>
              </Col>
              <Col span={8}>
                <Card><Statistic title="最佳实践" value={solution.best_practices_count} prefix={<CheckCircleOutlined />} /></Card>
              </Col>
              <Col span={8}>
                <Card><Statistic title="KPI基准数" value={Object.keys(solution.kpi_benchmarks || {}).length} /></Card>
              </Col>
            </Row>

            <Card title={solution.name}>
              <Space direction="vertical" style={{ width: '100%' }}>
                <Alert type="info" message={solution.description} />
                <Title level={5}>KPI 基准值</Title>
                <Row gutter={16}>
                  {Object.entries(solution.kpi_benchmarks || {}).map(([k, v]) => (
                    <Col span={6} key={k}>
                      <Card size="small">
                        <Statistic title={k} value={typeof v === 'number' ? v.toFixed(2) : v} />
                      </Card>
                    </Col>
                  ))}
                </Row>
                <Button
                  type="primary"
                  icon={<CheckCircleOutlined />}
                  onClick={handleApply}
                  style={{ marginTop: 8 }}
                >
                  应用到门店 {storeId}
                </Button>
              </Space>
            </Card>
          </>
        )}

        {applyResult && (
          <Card title="应用结果" size="small">
            <pre style={{ fontSize: 12, margin: 0 }}>{JSON.stringify(applyResult, null, 2)}</pre>
          </Card>
        )}
      </Space>
    </Spin>
  );
};

export default IndustrySolutionsPage;
