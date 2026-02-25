import React, { useState, useCallback, useEffect } from 'react';
import {
  Card, Col, Row, Select, Tabs, Statistic, Table, Tag,
  Button, Space, Modal, Form, Input, DatePicker, Popconfirm,
} from 'antd';
import { PlusOutlined, ReloadOutlined, ScanOutlined, WarningOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import dayjs from 'dayjs';
import { apiClient } from '../services/api';
import { handleApiError, showSuccess } from '../utils/message';

const { Option } = Select;

const licenseTypeLabel: Record<string, string> = {
  food_business: '食品经营许可证',
  health_certificate: '健康证',
  fire_safety: '消防安全证',
  business_license: '营业执照',
  liquor_license: '酒类经营许可证',
  other: '其他',
};
const statusColor: Record<string, string> = {
  valid: 'green', expire_soon: 'orange', expired: 'red', unknown: 'default',
};
const statusLabel: Record<string, string> = {
  valid: '有效', expire_soon: '即将到期', expired: '已过期', unknown: '未知',
};

const CompliancePage: React.FC = () => {
  const [selectedStore, setSelectedStore] = useState('');
  const [stores, setStores] = useState<any[]>([]);
  const [licenses, setLicenses] = useState<any[]>([]);
  const [summary, setSummary] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [scanning, setScanning] = useState(false);
  const [addModal, setAddModal] = useState(false);
  const [form] = Form.useForm();

  const loadStores = useCallback(async () => {
    try {
      const res = await apiClient.get('/stores');
      setStores(res.data?.stores || res.data || []);
    } catch (err: any) { handleApiError(err, '加载门店失败'); }
  }, []);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const params: any = {};
      if (selectedStore) params.store_id = selectedStore;
      const [lic, sum] = await Promise.allSettled([
        apiClient.get('/compliance/licenses', { params }),
        apiClient.get('/compliance/summary', { params }),
      ]);
      if (lic.status === 'fulfilled') setLicenses(lic.value.data || []);
      if (sum.status === 'fulfilled') setSummary(sum.value.data);
    } catch (err: any) { handleApiError(err, '加载合规数据失败'); }
    finally { setLoading(false); }
  }, [selectedStore]);

  useEffect(() => { loadStores(); }, [loadStores]);
  useEffect(() => { loadData(); }, [loadData]);

  const scanStore = async () => {
    setScanning(true);
    try {
      const res = selectedStore
        ? await apiClient.post(`/compliance/scan/${selectedStore}`)
        : await apiClient.post('/compliance/scan-all');
      const expiring = res.data?.expiring?.length || 0;
      const expired = res.data?.expired?.length || 0;
      showSuccess(`扫描完成：${expiring} 个即将到期，${expired} 个已过期`);
      loadData();
    } catch (err: any) { handleApiError(err, '扫描失败'); }
    finally { setScanning(false); }
  };

  const addLicense = async (values: any) => {
    try {
      await apiClient.post('/compliance/licenses', {
        ...values,
        store_id: selectedStore || values.store_id,
        expiry_date: values.expiry_date?.format('YYYY-MM-DD'),
        issue_date: values.issue_date?.format('YYYY-MM-DD'),
        remind_days_before: values.remind_days_before || 30,
      });
      showSuccess('证照已添加');
      setAddModal(false);
      form.resetFields();
      loadData();
    } catch (err: any) { handleApiError(err, '添加失败'); }
  };

  const deleteLicense = async (id: string) => {
    try {
      await apiClient.delete(`/compliance/licenses/${id}`);
      showSuccess('已删除');
      loadData();
    } catch (err: any) { handleApiError(err, '删除失败'); }
  };

  const columns: ColumnsType<any> = [
    { title: '证照名称', dataIndex: 'license_name', key: 'license_name' },
    { title: '类型', dataIndex: 'license_type', key: 'license_type', render: (v: string) => licenseTypeLabel[v] || v },
    { title: '证照号', dataIndex: 'license_number', key: 'license_number', render: (v: string) => v || '-' },
    { title: '持有人', dataIndex: 'holder_name', key: 'holder_name', render: (v: string) => v || '-' },
    { title: '到期日', dataIndex: 'expiry_date', key: 'expiry_date' },
    {
      title: '状态', dataIndex: 'status', key: 'status',
      render: (v: string) => <Tag color={statusColor[v] || 'default'}>{statusLabel[v] || v}</Tag>,
    },
    { title: '门店', dataIndex: 'store_id', key: 'store_id', render: (v: string) => v || '-' },
    {
      title: '操作', key: 'actions',
      render: (_: any, r: any) => (
        <Popconfirm title="确认删除？" onConfirm={() => deleteLicense(r.id)}>
          <Button size="small" danger>删除</Button>
        </Popconfirm>
      ),
    },
  ];

  const expireSoon = licenses.filter(l => l.status === 'expire_soon');
  const expired = licenses.filter(l => l.status === 'expired');

  const tabItems = [
    {
      key: 'summary', label: '合规汇总',
      children: (
        <div>
          <Row gutter={16} style={{ marginBottom: 16 }}>
            <Col span={5}><Card size="small"><Statistic title="总证照数" value={summary?.total ?? licenses.length} /></Card></Col>
            <Col span={5}><Card size="small"><Statistic title="有效" value={summary?.valid ?? '--'} valueStyle={{ color: '#52c41a' }} /></Card></Col>
            <Col span={5}><Card size="small"><Statistic title="即将到期" value={summary?.expire_soon ?? expireSoon.length} valueStyle={{ color: '#fa8c16' }} /></Card></Col>
            <Col span={5}><Card size="small"><Statistic title="已过期" value={summary?.expired ?? expired.length} valueStyle={{ color: '#ff4d4f' }} /></Card></Col>
            <Col span={4}><Card size="small"><Statistic title="未知" value={summary?.unknown ?? '--'} /></Card></Col>
          </Row>
          {expireSoon.length > 0 && (
            <Table
              title={() => <span style={{ color: '#fa8c16' }}><WarningOutlined /> 即将到期证照</span>}
              columns={columns.filter(c => c.key !== 'actions')}
              dataSource={expireSoon}
              rowKey="id"
              size="small"
              pagination={false}
            />
          )}
        </div>
      ),
    },
    {
      key: 'all', label: `全部证照 (${licenses.length})`,
      children: <Table columns={columns} dataSource={licenses} rowKey="id" loading={loading} size="small" />,
    },
  ];

  return (
    <div>
      <Space wrap style={{ marginBottom: 16 }}>
        <Select value={selectedStore} onChange={setSelectedStore} style={{ width: 160 }} placeholder="全部门店" allowClear>
          {stores.map((s: any) => (
            <Option key={s.store_id || s.id} value={s.store_id || s.id}>{s.name || s.store_id || s.id}</Option>
          ))}
        </Select>
        <Button icon={<ReloadOutlined />} onClick={loadData}>刷新</Button>
        <Button icon={<ScanOutlined />} loading={scanning} onClick={scanStore}>扫描到期证照</Button>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setAddModal(true)}>添加证照</Button>
      </Space>

      <Card><Tabs items={tabItems} /></Card>

      <Modal title="添加证照" open={addModal} onCancel={() => setAddModal(false)} footer={null} width={560}>
        <Form form={form} layout="vertical" onFinish={addLicense}>
          {!selectedStore && (
            <Form.Item name="store_id" label="门店ID" rules={[{ required: true }]}><Input /></Form.Item>
          )}
          <Form.Item name="license_name" label="证照名称" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="license_type" label="证照类型" rules={[{ required: true }]}>
            <Select>
              {Object.entries(licenseTypeLabel).map(([k, v]) => <Option key={k} value={k}>{v}</Option>)}
            </Select>
          </Form.Item>
          <Form.Item name="license_number" label="证照号"><Input /></Form.Item>
          <Form.Item name="holder_name" label="持有人姓名"><Input /></Form.Item>
          <Form.Item name="expiry_date" label="到期日期" rules={[{ required: true }]}><DatePicker style={{ width: '100%' }} /></Form.Item>
          <Form.Item name="issue_date" label="发证日期"><DatePicker style={{ width: '100%' }} /></Form.Item>
          <Form.Item name="remind_days_before" label="提前提醒天数" initialValue={30}>
            <Select>
              <Option value={7}>7天</Option>
              <Option value={14}>14天</Option>
              <Option value={30}>30天</Option>
              <Option value={60}>60天</Option>
            </Select>
          </Form.Item>
          <Form.Item name="notes" label="备注"><Input.TextArea rows={2} /></Form.Item>
          <Form.Item><Button type="primary" htmlType="submit" block>添加</Button></Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default CompliancePage;
