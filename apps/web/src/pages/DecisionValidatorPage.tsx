import React, { useState, useCallback } from 'react';
import {
  Card, Row, Col, Tabs, Table, Tag, Space, Button, Form, Input,
  Select, Spin, Typography, Alert, Progress, Descriptions, InputNumber, Statistic
} from 'antd';
import { CheckCircleOutlined, CloseCircleOutlined, WarningOutlined, BulbOutlined } from '@ant-design/icons';
import { apiClient } from '../services/api';
import { handleApiError } from '../utils/message';

const { Title } = Typography;
const { Option } = Select;

interface ValidationResult {
  result: string;
  confidence: number;
  violations: string[];
  recommendations: string[];
  validated_at: string;
}

interface BatchSummary { approved: number; rejected: number; warnings: number; }
interface BatchResult { store_id: string; decision_type: string; validation: ValidationResult; }
interface Rule { name: string; description: string; }
interface AnomalyResult { is_anomaly: boolean; metric_name: string; current_value: number; threshold: number; }

const resultColor: Record<string, string> = { approved: 'green', rejected: 'red', warning: 'orange' };
const resultLabel: Record<string, string> = { approved: '通过', rejected: '拒绝', warning: '警告' };

const DecisionValidatorPage: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [singleResult, setSingleResult] = useState<ValidationResult | null>(null);
  const [batchSummary, setBatchSummary] = useState<BatchSummary | null>(null);
  const [batchResults, setBatchResults] = useState<BatchResult[]>([]);
  const [rules, setRules] = useState<Rule[]>([]);
  const [anomalyResult, setAnomalyResult] = useState<AnomalyResult | null>(null);
  const [singleForm] = Form.useForm();
  const [anomalyForm] = Form.useForm();

  const loadRules = useCallback(async () => {
    setLoading(true);
    try {
      const res = await apiClient.get('/api/v1/validator/rules');
      setRules(res.data.rules || []);
    } catch (err) { handleApiError(err); }
    finally { setLoading(false); }
  }, []);

  const handleSingleValidate = async (values: Record<string, unknown>) => {
    setLoading(true);
    try {
      let suggestion = values.ai_suggestion;
      try { suggestion = JSON.parse(values.ai_suggestion as string); } catch { /* keep as string */ }
      const res = await apiClient.post('/api/v1/validator/validate', {
        store_id: values.store_id,
        decision_type: values.decision_type,
        ai_suggestion: suggestion,
      });
      setSingleResult(res.data.validation);
    } catch (err) { handleApiError(err); }
    finally { setLoading(false); }
  };

  const handleBatchValidate = async () => {
    setLoading(true);
    try {
      const payload = [
        { store_id: 'STORE001', decision_type: 'pricing', ai_suggestion: { price_change: 0.1 } },
        { store_id: 'STORE001', decision_type: 'staffing', ai_suggestion: { headcount_change: -2 } },
        { store_id: 'STORE002', decision_type: 'inventory', ai_suggestion: { reorder_qty: 500 } },
      ];
      const res = await apiClient.post('/api/v1/validator/validate/batch', payload);
      setBatchSummary(res.data.summary);
      setBatchResults(res.data.results || []);
    } catch (err) { handleApiError(err); }
    finally { setLoading(false); }
  };

  const handleAnomalyDetect = async (values: Record<string, unknown>) => {
    setLoading(true);
    try {
      const res = await apiClient.post('/api/v1/validator/anomaly/detect', values);
      setAnomalyResult(res.data);
    } catch (err) { handleApiError(err); }
    finally { setLoading(false); }
  };

  const batchColumns = [
    { title: '门店', dataIndex: 'store_id', key: 'store_id' },
    { title: '决策类型', dataIndex: 'decision_type', key: 'decision_type' },
    {
      title: '结果', key: 'result',
      render: (_: unknown, r: BatchResult) => (
        <Tag color={resultColor[r.validation?.result] || 'default'}>
          {resultLabel[r.validation?.result] || r.validation?.result}
        </Tag>
      ),
    },
    {
      title: '置信度', key: 'confidence',
      render: (_: unknown, r: BatchResult) => (
        <Progress percent={+(r.validation?.confidence * 100).toFixed(1)} size="small" style={{ width: 100 }} />
      ),
    },
  ];

  const ruleColumns = [
    { title: '规则名称', dataIndex: 'name', key: 'name', width: 200 },
    { title: '描述', dataIndex: 'description', key: 'description' },
  ];

  return (
    <Spin spinning={loading}>
      <Space direction="vertical" size="large" style={{ width: '100%' }}>
        <Title level={4} style={{ margin: 0 }}>决策验证</Title>

        <Card>
          <Tabs
            items={[
              {
                key: 'single',
                label: '单条验证',
                children: (
                  <Row gutter={24}>
                    <Col span={12}>
                      <Form form={singleForm} layout="vertical" onFinish={handleSingleValidate}>
                        <Form.Item name="store_id" label="门店ID" initialValue="STORE001" rules={[{ required: true }]}>
                          <Select>
                            <Option value="STORE001">STORE001</Option>
                            <Option value="STORE002">STORE002</Option>
                          </Select>
                        </Form.Item>
                        <Form.Item name="decision_type" label="决策类型" rules={[{ required: true }]}>
                          <Select placeholder="选择决策类型">
                            <Option value="pricing">定价调整</Option>
                            <Option value="staffing">人员调配</Option>
                            <Option value="inventory">库存补货</Option>
                            <Option value="promotion">促销活动</Option>
                          </Select>
                        </Form.Item>
                        <Form.Item name="ai_suggestion" label="AI建议（JSON）" rules={[{ required: true }]}>
                          <Input.TextArea rows={4} placeholder='{"price_change": 0.1}' />
                        </Form.Item>
                        <Button type="primary" htmlType="submit" icon={<CheckCircleOutlined />}>验证决策</Button>
                      </Form>
                    </Col>
                    <Col span={12}>
                      {singleResult && (
                        <Card size="small" title="验证结果">
                          <Descriptions column={1} size="small">
                            <Descriptions.Item label="结果">
                              <Tag color={resultColor[singleResult.result]}>{resultLabel[singleResult.result] || singleResult.result}</Tag>
                            </Descriptions.Item>
                            <Descriptions.Item label="置信度">
                              <Progress percent={+(singleResult.confidence * 100).toFixed(1)} size="small" style={{ width: 150 }} />
                            </Descriptions.Item>
                          </Descriptions>
                          {singleResult.violations?.length > 0 && (
                            <Alert
                              type="error"
                              message="违规项"
                              description={singleResult.violations.join('；')}
                              style={{ marginTop: 8 }}
                            />
                          )}
                          {singleResult.recommendations?.length > 0 && (
                            <Alert
                              type="info"
                              icon={<BulbOutlined />}
                              message="建议"
                              description={singleResult.recommendations.join('；')}
                              style={{ marginTop: 8 }}
                            />
                          )}
                        </Card>
                      )}
                    </Col>
                  </Row>
                ),
              },
              {
                key: 'batch',
                label: '批量验证',
                children: (
                  <Space direction="vertical" style={{ width: '100%' }}>
                    <Button type="primary" onClick={handleBatchValidate}>运行示例批量验证</Button>
                    {batchSummary && (
                      <Row gutter={16}>
                        <Col span={8}><Card><Statistic title="通过" value={batchSummary.approved} valueStyle={{ color: '#52c41a' }} /></Card></Col>
                        <Col span={8}><Card><Statistic title="拒绝" value={batchSummary.rejected} valueStyle={{ color: '#ff4d4f' }} /></Card></Col>
                        <Col span={8}><Card><Statistic title="警告" value={batchSummary.warnings} valueStyle={{ color: '#faad14' }} /></Card></Col>
                      </Row>
                    )}
                    <Table dataSource={batchResults} columns={batchColumns} rowKey="store_id" size="small" pagination={false} />
                  </Space>
                ),
              },
              {
                key: 'rules',
                label: '验证规则',
                children: (
                  <Space direction="vertical" style={{ width: '100%' }}>
                    <Button onClick={loadRules}>加载规则列表</Button>
                    <Table dataSource={rules} columns={ruleColumns} rowKey="name" size="small" pagination={{ pageSize: 10 }} />
                  </Space>
                ),
              },
              {
                key: 'anomaly',
                label: '异常检测',
                children: (
                  <Row gutter={24}>
                    <Col span={12}>
                      <Form form={anomalyForm} layout="vertical" onFinish={handleAnomalyDetect}>
                        <Form.Item name="store_id" label="门店ID" initialValue="STORE001" rules={[{ required: true }]}>
                          <Input />
                        </Form.Item>
                        <Form.Item name="metric_name" label="指标名称" rules={[{ required: true }]}>
                          <Select placeholder="选择指标">
                            <Option value="revenue">营收</Option>
                            <Option value="orders">订单数</Option>
                            <Option value="avg_order_value">客单价</Option>
                            <Option value="staff_count">员工数</Option>
                          </Select>
                        </Form.Item>
                        <Form.Item name="current_value" label="当前值" rules={[{ required: true }]}>
                          <InputNumber style={{ width: '100%' }} />
                        </Form.Item>
                        <Button type="primary" htmlType="submit" icon={<WarningOutlined />}>检测异常</Button>
                      </Form>
                    </Col>
                    <Col span={12}>
                      {anomalyResult && (
                        <Alert
                          type={anomalyResult.is_anomaly ? 'error' : 'success'}
                          icon={anomalyResult.is_anomaly ? <CloseCircleOutlined /> : <CheckCircleOutlined />}
                          message={anomalyResult.is_anomaly ? '检测到异常' : '正常范围内'}
                          description={
                            <Descriptions column={1} size="small">
                              <Descriptions.Item label="指标">{anomalyResult.metric_name}</Descriptions.Item>
                              <Descriptions.Item label="当前值">{anomalyResult.current_value}</Descriptions.Item>
                              <Descriptions.Item label="阈值">{anomalyResult.threshold}</Descriptions.Item>
                            </Descriptions>
                          }
                        />
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

export default DecisionValidatorPage;
