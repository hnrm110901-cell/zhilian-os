import React, { useState, useCallback, useEffect } from 'react';
import {
  Card, Col, Row, Select, Tabs, Statistic, Table, Tag,
  Button, Space, Modal, Form, Input, Upload, message,
} from 'antd';
import { PlusOutlined, UploadOutlined, ReloadOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { apiClient } from '../services/api';
import { handleApiError, showSuccess } from '../utils/message';

const { Option } = Select;

const QualityManagementPage: React.FC = () => {
  const [selectedStore, setSelectedStore] = useState('STORE001');
  const [stores, setStores] = useState<any[]>([]);
  const [inspections, setInspections] = useState<any[]>([]);
  const [summary, setSummary] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [inspectModal, setInspectModal] = useState(false);
  const [inspecting, setInspecting] = useState(false);
  const [form] = Form.useForm();
  const [imageB64, setImageB64] = useState('');

  const loadStores = useCallback(async () => {
    try {
      const res = await apiClient.get('/stores');
      setStores(res.data?.stores || res.data || []);
    } catch (err: any) { handleApiError(err, '加载门店失败'); }
  }, []);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [insp, sum] = await Promise.allSettled([
        apiClient.get(`/quality/inspections/${selectedStore}`, { params: { limit: 50 } }),
        apiClient.get(`/quality/summary/${selectedStore}`),
      ]);
      if (insp.status === 'fulfilled') setInspections(insp.value.data || []);
      if (sum.status === 'fulfilled') setSummary(sum.value.data);
    } catch (err: any) { handleApiError(err, '加载质检数据失败'); }
    finally { setLoading(false); }
  }, [selectedStore]);

  useEffect(() => { loadStores(); }, [loadStores]);
  useEffect(() => { loadData(); }, [loadData]);

  const submitInspection = async (values: any) => {
    if (!imageB64) { message.warning('请上传菜品图片'); return; }
    setInspecting(true);
    try {
      const res = await apiClient.post('/quality/inspect', {
        store_id: selectedStore,
        dish_name: values.dish_name,
        dish_id: values.dish_id,
        image_b64: imageB64,
        media_type: 'image/jpeg',
      });
      showSuccess(`质检完成，评分：${res.data?.data?.score ?? '--'}`);
      setInspectModal(false);
      form.resetFields();
      setImageB64('');
      loadData();
    } catch (err: any) { handleApiError(err, '质检失败'); }
    finally { setInspecting(false); }
  };

  const handleImageUpload = (file: File) => {
    const reader = new FileReader();
    reader.onload = (e) => setImageB64((e.target?.result as string)?.split(',')[1] || '');
    reader.readAsDataURL(file);
    return false; // prevent auto upload
  };

  const columns: ColumnsType<any> = [
    { title: '菜品', dataIndex: 'dish_name', key: 'dish_name' },
    {
      title: '评分', dataIndex: 'score', key: 'score',
      render: (v: number) => (
        <span style={{ color: v >= 80 ? '#52c41a' : v >= 60 ? '#fa8c16' : '#ff4d4f', fontWeight: 600 }}>
          {v ?? '--'}
        </span>
      ),
    },
    {
      title: '状态', dataIndex: 'status', key: 'status',
      render: (v: string) => <Tag color={v === 'pass' ? 'green' : v === 'fail' ? 'red' : 'orange'}>{v === 'pass' ? '合格' : v === 'fail' ? '不合格' : v || '-'}</Tag>,
    },
    { title: '问题', dataIndex: 'issues', key: 'issues', render: (v: string[]) => v?.join('、') || '-', ellipsis: true },
    { title: '建议', dataIndex: 'suggestions', key: 'suggestions', render: (v: string[]) => v?.join('、') || '-', ellipsis: true },
    { title: '时间', dataIndex: 'created_at', key: 'created_at', render: (v: string) => v?.slice(0, 16) || '-' },
  ];

  const tabItems = [
    {
      key: 'summary', label: '质检汇总',
      children: (
        <Row gutter={16}>
          <Col span={6}><Card size="small"><Statistic title="合格率" value={((summary?.pass_rate || 0) * 100).toFixed(1)} suffix="%" valueStyle={{ color: '#52c41a' }} /></Card></Col>
          <Col span={6}><Card size="small"><Statistic title="平均评分" value={summary?.avg_score?.toFixed(1) ?? '--'} /></Card></Col>
          <Col span={6}><Card size="small"><Statistic title="总质检次数" value={summary?.total_inspections ?? inspections.length} /></Card></Col>
          <Col span={6}><Card size="small"><Statistic title="不合格次数" value={summary?.fail_count ?? '--'} valueStyle={{ color: '#ff4d4f' }} /></Card></Col>
        </Row>
      ),
    },
    {
      key: 'records', label: `质检记录 (${inspections.length})`,
      children: <Table columns={columns} dataSource={inspections} rowKey={(r, i) => `${r.id || i}`} loading={loading} size="small" />,
    },
  ];

  return (
    <div>
      <Space wrap style={{ marginBottom: 16 }}>
        <Select value={selectedStore} onChange={setSelectedStore} style={{ width: 160 }}>
          {stores.length > 0 ? stores.map((s: any) => (
            <Option key={s.store_id || s.id} value={s.store_id || s.id}>{s.name || s.store_id || s.id}</Option>
          )) : <Option value="STORE001">STORE001</Option>}
        </Select>
        <Button icon={<ReloadOutlined />} onClick={loadData}>刷新</Button>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setInspectModal(true)}>发起质检</Button>
      </Space>

      <Card><Tabs items={tabItems} /></Card>

      <Modal title="发起菜品质检" open={inspectModal} onCancel={() => setInspectModal(false)} footer={null}>
        <Form form={form} layout="vertical" onFinish={submitInspection}>
          <Form.Item name="dish_name" label="菜品名称" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="dish_id" label="菜品ID"><Input placeholder="可选" /></Form.Item>
          <Form.Item label="菜品图片" required>
            <Upload beforeUpload={handleImageUpload} maxCount={1} accept="image/*" listType="picture">
              <Button icon={<UploadOutlined />}>上传图片</Button>
            </Upload>
          </Form.Item>
          <Form.Item><Button type="primary" htmlType="submit" loading={inspecting} block>提交质检</Button></Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default QualityManagementPage;
