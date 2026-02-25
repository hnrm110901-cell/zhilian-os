import React, { useState, useCallback, useEffect } from 'react';
import { Card, Button, Form, Input, InputNumber, Select, Statistic, Row, Col, Table, Tag, Tabs, Space } from 'antd';
import { ExperimentOutlined, SearchOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { apiClient } from '../services/api';
import { handleApiError, showSuccess } from '../utils/message';

const { Option } = Select;

const EmbeddingPage: React.FC = () => {
  const [modelStatus, setModelStatus] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [training, setTraining] = useState(false);
  const [similarDishes, setSimilarDishes] = useState<any[]>([]);
  const [recommendations, setRecommendations] = useState<any[]>([]);
  const [similarityResult, setSimilarityResult] = useState<number | null>(null);
  const [trainForm] = Form.useForm();
  const [simForm] = Form.useForm();
  const [dishForm] = Form.useForm();
  const [recForm] = Form.useForm();

  const loadStatus = useCallback(async () => {
    setLoading(true);
    try {
      const res = await apiClient.get('/embedding/model/status');
      setModelStatus(res.data);
    } catch (err: any) {
      handleApiError(err, '加载模型状态失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadStatus(); }, [loadStatus]);

  const trainModel = async (values: any) => {
    setTraining(true);
    try {
      await apiClient.post('/embedding/train', values);
      showSuccess('模型训练已启动');
      trainForm.resetFields();
      loadStatus();
    } catch (err: any) {
      handleApiError(err, '训练失败');
    } finally {
      setTraining(false);
    }
  };

  const calcSimilarity = async (values: any) => {
    try {
      const res = await apiClient.post('/embedding/similarity', values);
      setSimilarityResult(res.data?.similarity ?? res.data);
    } catch (err: any) {
      handleApiError(err, '计算相似度失败');
    }
  };

  const findSimilarDishes = async (values: any) => {
    try {
      const res = await apiClient.post('/embedding/similar-dishes', values);
      setSimilarDishes(res.data?.dishes || res.data || []);
    } catch (err: any) {
      handleApiError(err, '查找相似菜品失败');
    }
  };

  const getRecommendations = async (values: any) => {
    try {
      const res = await apiClient.post('/embedding/recommend', values);
      setRecommendations(res.data?.recommendations || res.data || []);
    } catch (err: any) {
      handleApiError(err, '获取推荐失败');
    }
  };

  const dishColumns: ColumnsType<any> = [
    { title: '菜品名称', dataIndex: 'name', key: 'name' },
    { title: '相似度', dataIndex: 'similarity', key: 'sim', render: (v: number) => v != null ? `${(v * 100).toFixed(1)}%` : '-' },
    { title: '分类', dataIndex: 'category', key: 'cat', render: (v: string) => v ? <Tag>{v}</Tag> : '-' },
    { title: '价格', dataIndex: 'price', key: 'price', render: (v: number) => v != null ? `¥${v.toFixed(2)}` : '-' },
  ];

  const tabItems = [
    {
      key: 'status',
      label: '模型状态',
      children: (
        <div>
          <Card loading={loading} style={{ marginBottom: 16 }}>
            {modelStatus && (
              <Row gutter={16}>
                <Col span={6}><Statistic title="模型版本" value={modelStatus.version || '-'} /></Col>
                <Col span={6}><Statistic title="向量维度" value={modelStatus.embedding_dim || 0} /></Col>
                <Col span={6}><Statistic title="训练样本数" value={modelStatus.training_samples || 0} /></Col>
                <Col span={6}><Statistic title="状态" valueRender={() => <Tag color={modelStatus.ready ? 'green' : 'orange'}>{modelStatus.ready ? '就绪' : '训练中'}</Tag>} value="" /></Col>
              </Row>
            )}
          </Card>
          <Card title="训练模型">
            <Form form={trainForm} layout="inline" onFinish={trainModel}>
              <Form.Item name="store_id" label="门店" initialValue="STORE001">
                <Select style={{ width: 120 }}>
                  <Option value="STORE001">门店001</Option>
                  <Option value="STORE002">门店002</Option>
                </Select>
              </Form.Item>
              <Form.Item name="epochs" label="训练轮数" initialValue={10}>
                <InputNumber min={1} max={100} />
              </Form.Item>
              <Form.Item>
                <Button type="primary" htmlType="submit" icon={<ExperimentOutlined />} loading={training}>开始训练</Button>
              </Form.Item>
            </Form>
          </Card>
        </div>
      ),
    },
    {
      key: 'similarity',
      label: '相似度计算',
      children: (
        <Card>
          <Form form={simForm} layout="vertical" onFinish={calcSimilarity} style={{ maxWidth: 500 }}>
            <Form.Item name="text1" label="文本1" rules={[{ required: true }]}><Input /></Form.Item>
            <Form.Item name="text2" label="文本2" rules={[{ required: true }]}><Input /></Form.Item>
            <Form.Item>
              <Button type="primary" htmlType="submit">计算相似度</Button>
            </Form.Item>
          </Form>
          {similarityResult !== null && (
            <Statistic title="相似度" value={`${(similarityResult * 100).toFixed(2)}%`} valueStyle={{ color: similarityResult > 0.7 ? '#52c41a' : '#fa8c16' }} />
          )}
        </Card>
      ),
    },
    {
      key: 'dishes',
      label: '相似菜品',
      children: (
        <Card>
          <Form form={dishForm} layout="inline" onFinish={findSimilarDishes} style={{ marginBottom: 16 }}>
            <Form.Item name="dish_id" label="菜品ID" rules={[{ required: true }]}><Input placeholder="输入菜品ID" /></Form.Item>
            <Form.Item name="top_k" label="数量" initialValue={5}><InputNumber min={1} max={20} /></Form.Item>
            <Form.Item><Button type="primary" htmlType="submit" icon={<SearchOutlined />}>查找</Button></Form.Item>
          </Form>
          <Table columns={dishColumns} dataSource={similarDishes} rowKey={(r, i) => r.dish_id || r.id || String(i)} />
        </Card>
      ),
    },
    {
      key: 'recommend',
      label: '个性化推荐',
      children: (
        <Card>
          <Form form={recForm} layout="inline" onFinish={getRecommendations} style={{ marginBottom: 16 }}>
            <Form.Item name="customer_id" label="顾客ID" rules={[{ required: true }]}><Input placeholder="顾客ID" /></Form.Item>
            <Form.Item name="store_id" label="门店" initialValue="STORE001">
              <Select style={{ width: 120 }}><Option value="STORE001">门店001</Option><Option value="STORE002">门店002</Option></Select>
            </Form.Item>
            <Form.Item name="top_k" label="数量" initialValue={5}><InputNumber min={1} max={20} /></Form.Item>
            <Form.Item><Button type="primary" htmlType="submit">获取推荐</Button></Form.Item>
          </Form>
          <Table columns={dishColumns} dataSource={recommendations} rowKey={(r, i) => r.dish_id || r.id || String(i)} />
        </Card>
      ),
    },
  ];

  return <Tabs items={tabItems} />;
};

export default EmbeddingPage;
