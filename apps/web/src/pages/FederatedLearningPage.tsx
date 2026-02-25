import React, { useState, useCallback } from 'react';
import {
  Card, Row, Col, Statistic, Tabs, Space, Button, Form,
  Select, Spin, Typography, Progress, Descriptions, InputNumber, Alert
} from 'antd';
import { CloudSyncOutlined, ExperimentOutlined, TrophyOutlined } from '@ant-design/icons';
import { apiClient } from '../services/api';
import { handleApiError, showSuccess } from '../utils/message';

const { Title } = Typography;
const { Option } = Select;

interface ModelStatus {
  model_type: string;
  version: string;
  participating_stores: number;
  performance_metrics: Record<string, number>;
  created_at: string;
}

interface Contribution {
  store_id: string;
  model_type: string;
  contribution_score: number;
  updates_submitted: number;
  last_update: string;
}

const FederatedLearningPage: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [modelStatus, setModelStatus] = useState<ModelStatus | null>(null);
  const [contribution, setContribution] = useState<Contribution | null>(null);
  const [aggregateResult, setAggregateResult] = useState<ModelStatus | null>(null);
  const [storeId, setStoreId] = useState('STORE001');
  const [modelType, setModelType] = useState('demand_forecast');
  const [submitForm] = Form.useForm();

  const loadModelStatus = useCallback(async () => {
    setLoading(true);
    try {
      const res = await apiClient.get(`/api/v1/federated/status/${modelType}`);
      setModelStatus(res.data);
    } catch (err) { handleApiError(err); }
    finally { setLoading(false); }
  }, [modelType]);

  const loadContribution = useCallback(async () => {
    setLoading(true);
    try {
      const res = await apiClient.get(`/api/v1/federated/contribution/${storeId}/${modelType}`);
      setContribution(res.data);
    } catch (err) { handleApiError(err); }
    finally { setLoading(false); }
  }, [storeId, modelType]);

  const handleAggregate = async () => {
    setLoading(true);
    try {
      const res = await apiClient.post('/api/v1/federated/aggregate', { model_type: modelType, min_participants: 2 });
      setAggregateResult(res.data);
      showSuccess('模型聚合完成');
    } catch (err) { handleApiError(err); }
    finally { setLoading(false); }
  };

  const handleSubmitUpdate = async (values: Record<string, unknown>) => {
    setLoading(true);
    try {
      await apiClient.post('/api/v1/federated/update/submit', {
        store_id: storeId,
        model_type: modelType,
        weights: { layer1: [0.1, 0.2, 0.3], layer2: [0.4, 0.5] },
        metrics: { accuracy: values.accuracy, loss: values.loss },
        sample_count: values.sample_count,
      });
      showSuccess('模型更新已提交');
      submitForm.resetFields();
    } catch (err) { handleApiError(err); }
    finally { setLoading(false); }
  };

  return (
    <Spin spinning={loading}>
      <Space direction="vertical" size="large" style={{ width: '100%' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <Title level={4} style={{ margin: 0 }}>联邦学习</Title>
          <Space>
            <Select value={storeId} onChange={setStoreId} style={{ width: 140 }}>
              <Option value="STORE001">门店 001</Option>
              <Option value="STORE002">门店 002</Option>
              <Option value="STORE003">门店 003</Option>
            </Select>
            <Select value={modelType} onChange={setModelType} style={{ width: 160 }}>
              <Option value="demand_forecast">需求预测</Option>
              <Option value="recommendation">推荐模型</Option>
              <Option value="pricing">定价模型</Option>
              <Option value="churn_prediction">流失预测</Option>
            </Select>
          </Space>
        </div>

        <Card>
          <Tabs
            items={[
              {
                key: 'status',
                label: '模型状态',
                children: (
                  <Space direction="vertical" style={{ width: '100%' }}>
                    <Button type="primary" icon={<ExperimentOutlined />} onClick={loadModelStatus}>查询模型状态</Button>
                    {modelStatus && (
                      <Row gutter={16}>
                        <Col span={6}><Card><Statistic title="模型版本" value={modelStatus.version} /></Card></Col>
                        <Col span={6}><Card><Statistic title="参与门店" value={modelStatus.participating_stores} /></Card></Col>
                        {Object.entries(modelStatus.performance_metrics || {}).map(([k, v]) => (
                          <Col span={6} key={k}>
                            <Card><Statistic title={k} value={typeof v === 'number' ? v.toFixed(4) : v} /></Card>
                          </Col>
                        ))}
                      </Row>
                    )}
                  </Space>
                ),
              },
              {
                key: 'submit',
                label: '提交更新',
                children: (
                  <Row gutter={24}>
                    <Col span={12}>
                      <Form form={submitForm} layout="vertical" onFinish={handleSubmitUpdate}>
                        <Form.Item name="accuracy" label="准确率" initialValue={0.85} rules={[{ required: true }]}>
                          <InputNumber min={0} max={1} step={0.01} style={{ width: '100%' }} />
                        </Form.Item>
                        <Form.Item name="loss" label="损失值" initialValue={0.15} rules={[{ required: true }]}>
                          <InputNumber min={0} step={0.001} style={{ width: '100%' }} />
                        </Form.Item>
                        <Form.Item name="sample_count" label="样本数量" initialValue={1000} rules={[{ required: true }]}>
                          <InputNumber min={1} style={{ width: '100%' }} />
                        </Form.Item>
                        <Button type="primary" htmlType="submit" icon={<CloudSyncOutlined />}>提交本地更新</Button>
                      </Form>
                    </Col>
                    <Col span={12}>
                      <Alert
                        type="info"
                        message="联邦学习说明"
                        description="各门店在本地训练模型后，仅上传模型权重（不上传原始数据），由中心节点聚合后下发全局模型，保护数据隐私。"
                      />
                    </Col>
                  </Row>
                ),
              },
              {
                key: 'aggregate',
                label: '模型聚合',
                children: (
                  <Space direction="vertical" style={{ width: '100%' }}>
                    <Button type="primary" icon={<CloudSyncOutlined />} onClick={handleAggregate}>触发全局聚合</Button>
                    {aggregateResult && (
                      <Card title="聚合结果" size="small">
                        <Descriptions column={2} size="small">
                          <Descriptions.Item label="模型类型">{aggregateResult.model_type}</Descriptions.Item>
                          <Descriptions.Item label="新版本">{aggregateResult.version}</Descriptions.Item>
                          <Descriptions.Item label="参与门店">{aggregateResult.participating_stores}</Descriptions.Item>
                          <Descriptions.Item label="创建时间">{aggregateResult.created_at}</Descriptions.Item>
                        </Descriptions>
                      </Card>
                    )}
                  </Space>
                ),
              },
              {
                key: 'contribution',
                label: '贡献度',
                children: (
                  <Space direction="vertical" style={{ width: '100%' }}>
                    <Button icon={<TrophyOutlined />} onClick={loadContribution}>查询贡献度</Button>
                    {contribution && (
                      <Card size="small">
                        <Descriptions column={2} size="small">
                          <Descriptions.Item label="门店">{contribution.store_id}</Descriptions.Item>
                          <Descriptions.Item label="模型">{contribution.model_type}</Descriptions.Item>
                          <Descriptions.Item label="贡献分">
                            <Progress percent={+(contribution.contribution_score * 100).toFixed(1)} size="small" style={{ width: 150 }} />
                          </Descriptions.Item>
                          <Descriptions.Item label="提交次数">{contribution.updates_submitted}</Descriptions.Item>
                          <Descriptions.Item label="最后更新">{contribution.last_update}</Descriptions.Item>
                        </Descriptions>
                      </Card>
                    )}
                  </Space>
                ),
              },
            ]}
          />
        </Card>
      </Space>
    </Spin>
  );
};

export default FederatedLearningPage;
