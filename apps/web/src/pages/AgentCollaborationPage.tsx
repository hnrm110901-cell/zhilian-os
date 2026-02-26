import React, { useState, useCallback, useEffect } from 'react';
import {
  Card, Row, Col, Statistic, Tabs, Space, Button, Form,
  Select, Spin, Typography, Descriptions, InputNumber, Progress, Input
} from 'antd';
import { ApartmentOutlined, SyncOutlined, WarningOutlined, BarChartOutlined } from '@ant-design/icons';
import { apiClient } from '../services/api';
import { handleApiError, showSuccess } from '../utils/message';

const { Title } = Typography;
const { Option } = Select;

interface CollaborationStatus {
  store_id: string;
  pending_decisions: number;
  active_conflicts: number;
  efficiency_score: number;
}

interface ConflictResult {
  conflict_id: string;
  strategy: string;
  approved_decisions: string[];
  rejected_decisions: string[];
  reason: string;
  resolved_at: string;
}

interface PerformanceResult {
  agent_type: string;
  total_decisions: number;
  success_rate: number;
  avg_benefit: number;
  conflict_rate: number;
}

const AgentCollaborationPage: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [storeId, setStoreId] = useState('STORE001');
  const [stores, setStores] = useState<any[]>([]);
  const [status, setStatus] = useState<CollaborationStatus | null>(null);
  const [conflictResult, setConflictResult] = useState<ConflictResult | null>(null);
  const [performance, setPerformance] = useState<PerformanceResult | null>(null);
  const [coordinateResult, setCoordinateResult] = useState<Record<string, unknown> | null>(null);
  const [submitForm] = Form.useForm();
  const [conflictForm] = Form.useForm();
  const [perfForm] = Form.useForm();

  const loadStores = useCallback(async () => {
    try {
      const res = await apiClient.get('/stores');
      setStores(res.data?.stores || res.data || []);
    } catch { /* ignore */ }
  }, []);

  const loadStatus = useCallback(async () => {
    setLoading(true);
    try {
      const res = await apiClient.get(`/api/v1/collaboration/status/${storeId}`);
      setStatus(res.data);
    } catch (err) { handleApiError(err); }
    finally { setLoading(false); }
  }, [storeId]);

  useEffect(() => { loadStores(); }, [loadStores]);

  const handleCoordinate = async () => {
    setLoading(true);
    try {
      const res = await apiClient.post('/api/v1/collaboration/coordinate', { store_id: storeId, time_window: 3600 });
      setCoordinateResult(res.data);
      showSuccess('协调完成');
    } catch (err) { handleApiError(err); }
    finally { setLoading(false); }
  };

  const handleSubmitDecision = async (values: Record<string, unknown>) => {
    setLoading(true);
    try {
      await apiClient.post('/api/v1/collaboration/decision/submit', {
        agent_type: values.agent_type,
        decision_id: `DEC_${Date.now()}`,
        action: values.action,
        resources_required: { budget: values.budget },
        expected_benefit: values.expected_benefit,
        priority: values.priority,
        constraints: [],
      });
      showSuccess('决策已提交');
      submitForm.resetFields();
    } catch (err) { handleApiError(err); }
    finally { setLoading(false); }
  };

  const handleResolveConflict = async (values: Record<string, unknown>) => {
    setLoading(true);
    try {
      const res = await apiClient.post('/api/v1/collaboration/conflict/resolve', {
        conflict_id: values.conflict_id,
        strategy: values.strategy,
      });
      setConflictResult(res.data);
      showSuccess('冲突已解决');
    } catch (err) { handleApiError(err); }
    finally { setLoading(false); }
  };

  const handleGetPerformance = async (values: Record<string, unknown>) => {
    setLoading(true);
    try {
      const res = await apiClient.post('/api/v1/collaboration/performance', values);
      setPerformance(res.data);
    } catch (err) { handleApiError(err); }
    finally { setLoading(false); }
  };

  return (
    <Spin spinning={loading}>
      <Space direction="vertical" size="large" style={{ width: '100%' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <Title level={4} style={{ margin: 0 }}>Agent协作</Title>
          <Space>
            <Select value={storeId} onChange={setStoreId} style={{ width: 140 }}>
              {stores.length > 0 ? stores.map((s: any) => (
                <Option key={s.store_id || s.id} value={s.store_id || s.id}>{s.name || s.store_id || s.id}</Option>
              )) : <Option value="STORE001">门店 001</Option>}
            </Select>
            <Button icon={<SyncOutlined />} onClick={loadStatus}>查询状态</Button>
          </Space>
        </div>

        {status && (
          <Row gutter={16}>
            <Col span={8}><Card><Statistic title="待处理决策" value={status.pending_decisions} prefix={<ApartmentOutlined />} /></Card></Col>
            <Col span={8}><Card><Statistic title="活跃冲突" value={status.active_conflicts} valueStyle={{ color: status.active_conflicts > 0 ? '#ff4d4f' : '#52c41a' }} prefix={<WarningOutlined />} /></Card></Col>
            <Col span={8}>
              <Card>
                <Statistic title="协作效率" value={+(status.efficiency_score * 100).toFixed(1)} suffix="%" prefix={<BarChartOutlined />} valueStyle={{ color: '#1890ff' }} />
              </Card>
            </Col>
          </Row>
        )}

        <Card>
          <Tabs
            items={[
              {
                key: 'submit',
                label: '提交决策',
                children: (
                  <Row gutter={24}>
                    <Col span={12}>
                      <Form form={submitForm} layout="vertical" onFinish={handleSubmitDecision}>
                        <Form.Item name="agent_type" label="Agent类型" rules={[{ required: true }]}>
                          <Select placeholder="选择Agent">
                            <Option value="inventory">库存Agent</Option>
                            <Option value="pricing">定价Agent</Option>
                            <Option value="staffing">排班Agent</Option>
                            <Option value="marketing">营销Agent</Option>
                          </Select>
                        </Form.Item>
                        <Form.Item name="action" label="操作描述" rules={[{ required: true }]}>
                          <Input placeholder="例：调整价格上浮10%" />
                        </Form.Item>
                        <Form.Item name="budget" label="所需预算（元）" initialValue={1000}>
                          <InputNumber min={0} style={{ width: '100%' }} />
                        </Form.Item>
                        <Form.Item name="expected_benefit" label="预期收益（元）" initialValue={5000}>
                          <InputNumber min={0} style={{ width: '100%' }} />
                        </Form.Item>
                        <Form.Item name="priority" label="优先级（1-10）" initialValue={5}>
                          <InputNumber min={1} max={10} style={{ width: '100%' }} />
                        </Form.Item>
                        <Button type="primary" htmlType="submit">提交决策</Button>
                      </Form>
                    </Col>
                    <Col span={12}>
                      <Button block onClick={handleCoordinate} icon={<ApartmentOutlined />} style={{ marginBottom: 16 }}>
                        触发协调（1小时窗口）
                      </Button>
                      {coordinateResult && (
                        <Card size="small" title="协调结果">
                          <pre style={{ fontSize: 12, margin: 0 }}>{JSON.stringify(coordinateResult, null, 2)}</pre>
                        </Card>
                      )}
                    </Col>
                  </Row>
                ),
              },
              {
                key: 'conflict',
                label: '冲突解决',
                children: (
                  <Row gutter={24}>
                    <Col span={12}>
                      <Form form={conflictForm} layout="vertical" onFinish={handleResolveConflict}>
                        <Form.Item name="conflict_id" label="冲突ID" rules={[{ required: true }]}>
                          <Input placeholder="输入冲突ID" />
                        </Form.Item>
                        <Form.Item name="strategy" label="解决策略">
                          <Select placeholder="选择策略（可选）">
                            <Option value="priority_based">优先级优先</Option>
                            <Option value="negotiation">协商</Option>
                            <Option value="optimization">优化</Option>
                            <Option value="escalation">升级处理</Option>
                          </Select>
                        </Form.Item>
                        <Button type="primary" htmlType="submit" icon={<WarningOutlined />}>解决冲突</Button>
                      </Form>
                    </Col>
                    <Col span={12}>
                      {conflictResult && (
                        <Card size="small" title="解决结果">
                          <Descriptions column={1} size="small">
                            <Descriptions.Item label="策略">{conflictResult.strategy}</Descriptions.Item>
                            <Descriptions.Item label="批准">{conflictResult.approved_decisions?.join(', ')}</Descriptions.Item>
                            <Descriptions.Item label="拒绝">{conflictResult.rejected_decisions?.join(', ')}</Descriptions.Item>
                            <Descriptions.Item label="原因">{conflictResult.reason}</Descriptions.Item>
                          </Descriptions>
                        </Card>
                      )}
                    </Col>
                  </Row>
                ),
              },
              {
                key: 'performance',
                label: '性能分析',
                children: (
                  <Row gutter={24}>
                    <Col span={12}>
                      <Form form={perfForm} layout="vertical" onFinish={handleGetPerformance}>
                        <Form.Item name="agent_type" label="Agent类型" rules={[{ required: true }]}>
                          <Select placeholder="选择Agent">
                            <Option value="inventory">库存Agent</Option>
                            <Option value="pricing">定价Agent</Option>
                            <Option value="staffing">排班Agent</Option>
                          </Select>
                        </Form.Item>
                        <Form.Item name="start_date" label="开始日期" initialValue="2026-01-01">
                          <Input type="date" />
                        </Form.Item>
                        <Form.Item name="end_date" label="结束日期" initialValue="2026-02-25">
                          <Input type="date" />
                        </Form.Item>
                        <Button type="primary" htmlType="submit" icon={<BarChartOutlined />}>查询性能</Button>
                      </Form>
                    </Col>
                    <Col span={12}>
                      {performance && (
                        <Card size="small" title="性能指标">
                          <Descriptions column={1} size="small">
                            <Descriptions.Item label="Agent">{performance.agent_type}</Descriptions.Item>
                            <Descriptions.Item label="总决策数">{performance.total_decisions}</Descriptions.Item>
                            <Descriptions.Item label="成功率">
                              <Progress percent={+(performance.success_rate * 100).toFixed(1)} size="small" style={{ width: 150 }} />
                            </Descriptions.Item>
                            <Descriptions.Item label="平均收益">{performance.avg_benefit?.toFixed(2)} 元</Descriptions.Item>
                            <Descriptions.Item label="冲突率">{(performance.conflict_rate * 100).toFixed(1)}%</Descriptions.Item>
                          </Descriptions>
                        </Card>
                      )}
                    </Col>
                  </Row>
                ),
              },
            ]}
          />
        </Card>
      </Space>
    </Spin>
  );
};

export default AgentCollaborationPage;
