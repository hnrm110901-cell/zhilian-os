import React, { useState, useCallback, useEffect } from 'react';
import { Card, Table, Button, Tag, Space, Statistic, Row, Col, Modal, Form, Input, Select } from 'antd';
import { PlusOutlined, LinkOutlined, DisconnectOutlined, SoundOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { apiClient } from '../services/api';
import { handleApiError, showSuccess } from '../utils/message';

const { Option } = Select;
const { TextArea } = Input;

const roleLabel: Record<string, string> = { front_of_house: '前厅', cashier: '收银', kitchen: '厨房' };
const roleColor: Record<string, string> = { front_of_house: 'blue', cashier: 'green', kitchen: 'orange' };

const VoiceDevicePage: React.FC = () => {
  const [devices, setDevices] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [registerVisible, setRegisterVisible] = useState(false);
  const [notifyVisible, setNotifyVisible] = useState(false);
  const [actionLoading, setActionLoading] = useState<Record<string, boolean>>({});
  const [registerForm] = Form.useForm();
  const [notifyForm] = Form.useForm();
  const [notifySubmitting, setNotifySubmitting] = useState(false);

  const loadDevices = useCallback(async () => {
    setLoading(true);
    try {
      const res = await apiClient.get('/voice/devices');
      setDevices(res.data?.devices || res.data || []);
    } catch (err: any) {
      handleApiError(err, '加载设备列表失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadDevices(); }, [loadDevices]);

  const registerDevice = async (values: any) => {
    try {
      await apiClient.post('/voice/devices/register', values);
      showSuccess('设备注册成功');
      setRegisterVisible(false);
      registerForm.resetFields();
      loadDevices();
    } catch (err: any) {
      handleApiError(err, '注册失败');
    }
  };

  const connectDevice = async (record: any) => {
    const key = `connect-${record.device_id}`;
    setActionLoading(prev => ({ ...prev, [key]: true }));
    try {
      await apiClient.post(`/voice/devices/${record.device_id}/connect`);
      showSuccess('已连接');
      loadDevices();
    } catch (err: any) {
      handleApiError(err, '连接失败');
    } finally {
      setActionLoading(prev => ({ ...prev, [key]: false }));
    }
  };

  const disconnectDevice = async (record: any) => {
    const key = `disconnect-${record.device_id}`;
    setActionLoading(prev => ({ ...prev, [key]: true }));
    try {
      await apiClient.post(`/voice/devices/${record.device_id}/disconnect`);
      showSuccess('已断开');
      loadDevices();
    } catch (err: any) {
      handleApiError(err, '断开失败');
    } finally {
      setActionLoading(prev => ({ ...prev, [key]: false }));
    }
  };

  const broadcastNotify = async (values: any) => {
    setNotifySubmitting(true);
    try {
      await apiClient.post('/voice/voice/notification/broadcast', {
        message: values.message,
        role: values.role || undefined,
        priority: values.priority || 'normal',
      });
      showSuccess('广播已发送');
      setNotifyVisible(false);
      notifyForm.resetFields();
    } catch (err: any) {
      handleApiError(err, '广播失败');
    } finally {
      setNotifySubmitting(false);
    }
  };

  const columns: ColumnsType<any> = [
    { title: '设备ID', dataIndex: 'device_id', key: 'device_id', ellipsis: true },
    { title: '型号', dataIndex: 'device_type', key: 'device_type' },
    { title: '角色', dataIndex: 'role', key: 'role', render: (v: string) => <Tag color={roleColor[v] || 'default'}>{roleLabel[v] || v}</Tag> },
    { title: '门店', dataIndex: 'store_id', key: 'store_id' },
    { title: '状态', dataIndex: 'connected', key: 'connected', render: (v: boolean) => <Tag color={v ? 'green' : 'default'}>{v ? '已连接' : '未连接'}</Tag> },
    {
      title: '操作', key: 'actions',
      render: (_: any, record: any) => (
        <Space>
          {record.connected
            ? <Button size="small" icon={<DisconnectOutlined />} loading={actionLoading[`disconnect-${record.device_id}`]} onClick={() => disconnectDevice(record)}>断开</Button>
            : <Button size="small" type="primary" icon={<LinkOutlined />} loading={actionLoading[`connect-${record.device_id}`]} onClick={() => connectDevice(record)}>连接</Button>
          }
        </Space>
      ),
    },
  ];

  const connected = devices.filter((d: any) => d.connected).length;

  return (
    <div>
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={6}><Card><Statistic title="设备总数" value={devices.length} /></Card></Col>
        <Col span={6}><Card><Statistic title="已连接" value={connected} /></Card></Col>
        <Col span={6}><Card><Statistic title="前厅设备" value={devices.filter((d: any) => d.role === 'front_of_house').length} /></Card></Col>
        <Col span={6}><Card><Statistic title="厨房设备" value={devices.filter((d: any) => d.role === 'kitchen').length} /></Card></Col>
      </Row>

      <Card
        title="Shokz 骨传导耳机管理"
        extra={
          <Space>
            <Button icon={<SoundOutlined />} onClick={() => setNotifyVisible(true)}>广播通知</Button>
            <Button type="primary" icon={<PlusOutlined />} onClick={() => setRegisterVisible(true)}>注册设备</Button>
          </Space>
        }
      >
        <Table columns={columns} dataSource={devices} rowKey={(r) => r.device_id} loading={loading} />
      </Card>

      <Modal title="注册设备" open={registerVisible} onCancel={() => setRegisterVisible(false)} onOk={() => registerForm.submit()} okText="注册">
        <Form form={registerForm} layout="vertical" onFinish={registerDevice}>
          <Form.Item name="device_id" label="设备ID" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="device_type" label="型号" rules={[{ required: true }]}>
            <Select>
              <Option value="opencomm_2">OpenComm 2</Option>
              <Option value="openrun_pro_2">OpenRun Pro 2</Option>
            </Select>
          </Form.Item>
          <Form.Item name="role" label="角色" rules={[{ required: true }]}>
            <Select>{Object.entries(roleLabel).map(([k, v]) => <Option key={k} value={k}>{v}</Option>)}</Select>
          </Form.Item>
          <Form.Item name="bluetooth_address" label="蓝牙地址" rules={[{ required: true }]}><Input placeholder="XX:XX:XX:XX:XX:XX" /></Form.Item>
          <Form.Item name="store_id" label="门店ID" rules={[{ required: true }]}><Input /></Form.Item>
        </Form>
      </Modal>

      <Modal title="广播语音通知" open={notifyVisible} onCancel={() => setNotifyVisible(false)} onOk={() => notifyForm.submit()} okText="发送" confirmLoading={notifySubmitting}>
        <Form form={notifyForm} layout="vertical" onFinish={broadcastNotify}>
          <Form.Item name="message" label="通知内容" rules={[{ required: true }]}><TextArea rows={3} /></Form.Item>
          <Form.Item name="role" label="目标角色（不选则全部）">
            <Select allowClear>{Object.entries(roleLabel).map(([k, v]) => <Option key={k} value={k}>{v}</Option>)}</Select>
          </Form.Item>
          <Form.Item name="priority" label="优先级" initialValue="normal">
            <Select>
              <Option value="normal">普通</Option>
              <Option value="high">高</Option>
              <Option value="urgent">紧急</Option>
            </Select>
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default VoiceDevicePage;
