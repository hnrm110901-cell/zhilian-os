import React, { useState, useEffect, useCallback } from 'react';
import {
  Card, Tabs, Table, Button, Modal, Form, Input, InputNumber,
  Select, Space, Popconfirm, Row, Col, Statistic,
} from 'antd';
import {
  PlusOutlined, EditOutlined, DeleteOutlined, ReloadOutlined,
} from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import ReactECharts from 'echarts-for-react';
import { apiClient } from '../services/api';
import { showSuccess, handleApiError, showLoading } from '../utils/message';

interface Competitor {
  id: number;
  name: string;
  market_share?: number;
  avg_price?: number;
  description?: string;
}

interface MarketShare {
  name: string;
  value: number;
}

interface PriceComparison {
  date: string;
  our_price: number;
  competitor_price: number;
}

interface PriceSensitivity {
  price: number;
  demand: number;
}

const CompetitiveAnalysis: React.FC = () => {
  const [competitors, setCompetitors] = useState<Competitor[]>([]);
  const [marketShare, setMarketShare] = useState<MarketShare[]>([]);
  const [priceComparison, setPriceComparison] = useState<PriceComparison[]>([]);
  const [priceSensitivity, setPriceSensitivity] = useState<PriceSensitivity[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalVisible, setModalVisible] = useState(false);
  const [editingItem, setEditingItem] = useState<Competitor | null>(null);
  const [selectedCompetitor, setSelectedCompetitor] = useState<number | undefined>();
  const [form] = Form.useForm();

  const loadCompetitors = useCallback(async () => {
    try {
      setLoading(true);
      const res = await apiClient.get('/api/v1/competitive/competitors');
      setCompetitors(res.data?.data || res.data || []);
    } catch (err: any) {
      handleApiError(err, '加载竞品列表失败');
    } finally {
      setLoading(false);
    }
  }, []);

  const loadMarketShare = useCallback(async () => {
    try {
      const res = await apiClient.get('/api/v1/competitive/market-share');
      setMarketShare(res.data?.data || res.data || []);
    } catch (err: any) {
      handleApiError(err, '加载市场份额失败');
    }
  }, []);

  const loadPriceComparison = useCallback(async (competitorId?: number) => {
    try {
      const params = competitorId ? { competitor_id: competitorId } : {};
      const res = await apiClient.get('/api/v1/competitive/price-comparison', { params });
      setPriceComparison(res.data?.data || res.data || []);
    } catch (err: any) {
      handleApiError(err, '加载价格对比失败');
    }
  }, []);

  const loadPriceSensitivity = useCallback(async () => {
    try {
      const res = await apiClient.get('/api/v1/competitive/price-sensitivity');
      setPriceSensitivity(res.data?.data || res.data || []);
    } catch (err: any) {
      handleApiError(err, '加载价格敏感度失败');
    }
  }, []);

  useEffect(() => {
    loadCompetitors();
    loadMarketShare();
    loadPriceComparison();
    loadPriceSensitivity();
  }, [loadCompetitors, loadMarketShare, loadPriceComparison, loadPriceSensitivity]);

  const handleAdd = () => {
    setEditingItem(null);
    form.resetFields();
    setModalVisible(true);
  };

  const handleEdit = (record: Competitor) => {
    setEditingItem(record);
    form.setFieldsValue(record);
    setModalVisible(true);
  };

  const handleDelete = async (id: number) => {
    const hide = showLoading('删除中...');
    try {
      await apiClient.delete(`/api/v1/competitive/competitors/${id}`);
      hide();
      showSuccess('删除成功');
      loadCompetitors();
    } catch (err: any) {
      hide();
      handleApiError(err, '删除失败');
    }
  };

  const handleModalOk = async () => {
    try {
      const values = await form.validateFields();
      const hide = showLoading(editingItem ? '更新中...' : '新增中...');
      try {
        if (editingItem) {
          await apiClient.put(`/api/v1/competitive/competitors/${editingItem.id}`, values);
        } else {
          await apiClient.post('/api/v1/competitive/competitors', values);
        }
        hide();
        showSuccess(editingItem ? '更新成功' : '新增成功');
        setModalVisible(false);
        loadCompetitors();
      } catch (err: any) {
        hide();
        handleApiError(err, '操作失败');
      }
    } catch (_) {}
  };

  const columns: ColumnsType<Competitor> = [
    { title: '竞品名称', dataIndex: 'name', key: 'name' },
    { title: '市场份额(%)', dataIndex: 'market_share', key: 'market_share', render: (v) => v != null ? `${v}%` : '-' },
    { title: '平均价格', dataIndex: 'avg_price', key: 'avg_price', render: (v) => v != null ? `¥${v}` : '-' },
    { title: '描述', dataIndex: 'description', key: 'description', ellipsis: true },
    {
      title: '操作', key: 'action',
      render: (_, record) => (
        <Space>
          <Button size="small" icon={<EditOutlined />} onClick={() => handleEdit(record)}>编辑</Button>
          <Popconfirm title="确认删除？" onConfirm={() => handleDelete(record.id)}>
            <Button size="small" danger icon={<DeleteOutlined />}>删除</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  const ourShare = marketShare.find(m => m.name === '我方' || m.name === 'us' || m.name === 'self');
  const totalShare = marketShare.reduce((s, m) => s + (m.value || 0), 0);

  const pieOption = {
    tooltip: { trigger: 'item', formatter: '{b}: {c}%' },
    legend: { orient: 'vertical', left: 'left' },
    series: [{
      type: 'pie', radius: '60%',
      data: marketShare.map(m => ({ name: m.name, value: m.value })),
    }],
  };

  const barOption = {
    tooltip: { trigger: 'axis' },
    legend: { data: ['我方价格', '竞品价格'] },
    xAxis: { type: 'category', data: priceComparison.map(d => d.date) },
    yAxis: { type: 'value', name: '价格(¥)' },
    series: [
      { name: '我方价格', type: 'bar', data: priceComparison.map(d => d.our_price) },
      { name: '竞品价格', type: 'bar', data: priceComparison.map(d => d.competitor_price) },
    ],
  };

  const lineOption = {
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'category', data: priceSensitivity.map(d => `¥${d.price}`) },
    yAxis: { type: 'value', name: '需求量' },
    series: [{ name: '需求量', type: 'line', smooth: true, data: priceSensitivity.map(d => d.demand) }],
  };

  const tabItems = [
    {
      key: 'competitors',
      label: '竞品管理',
      children: (
        <>
          <div style={{ marginBottom: 16 }}>
            <Space>
              <Button type="primary" icon={<PlusOutlined />} onClick={handleAdd}>新增竞品</Button>
              <Button icon={<ReloadOutlined />} onClick={loadCompetitors}>刷新</Button>
            </Space>
          </div>
          <Table columns={columns} dataSource={competitors} rowKey="id" loading={loading} />
        </>
      ),
    },
    {
      key: 'price-comparison',
      label: '价格对比',
      children: (
        <>
          <div style={{ marginBottom: 16 }}>
            <Select
              placeholder="选择竞品"
              allowClear
              style={{ width: 200 }}
              onChange={(val) => { setSelectedCompetitor(val); loadPriceComparison(val); }}
              value={selectedCompetitor}
              options={competitors.map(c => ({ label: c.name, value: c.id }))}
            />
          </div>
          <ReactECharts option={barOption} style={{ height: 350 }} />
        </>
      ),
    },
    {
      key: 'market-share',
      label: '市场份额',
      children: <ReactECharts option={pieOption} style={{ height: 400 }} />,
    },
    {
      key: 'price-sensitivity',
      label: '价格敏感度',
      children: <ReactECharts option={lineOption} style={{ height: 350 }} />,
    },
  ];

  return (
    <div>
      <Row gutter={16} style={{ marginBottom: 24 }}>
        <Col span={6}>
          <Card>
            <Statistic title="竞品数量" value={competitors.length} suffix="家" />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="我方市场份额"
              value={ourShare?.value ?? (totalShare > 0 ? '-' : 0)}
              suffix="%"
            />
          </Card>
        </Col>
      </Row>

      <Card>
        <Tabs items={tabItems} />
      </Card>

      <Modal
        title={editingItem ? '编辑竞品' : '新增竞品'}
        open={modalVisible}
        onOk={handleModalOk}
        onCancel={() => setModalVisible(false)}
        destroyOnClose
      >
        <Form form={form} layout="vertical">
          <Form.Item name="name" label="竞品名称" rules={[{ required: true, message: '请输入竞品名称' }]}>
            <Input />
          </Form.Item>
          <Form.Item name="market_share" label="市场份额(%)">
            <InputNumber min={0} max={100} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="avg_price" label="平均价格(¥)">
            <InputNumber min={0} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <Input.TextArea rows={3} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default CompetitiveAnalysis;
