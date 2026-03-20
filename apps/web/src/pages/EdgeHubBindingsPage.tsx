import React, { useState, useEffect } from 'react';
import {
  Card, Table, Tag, Button, Modal, Form, Input, InputNumber, Select,
  Space, Popconfirm, message, Empty, Spin, Badge,
} from 'antd';
import { PlusOutlined, EditOutlined, DeleteOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
import { useSearchParams } from 'react-router-dom';
import { apiClient, handleApiError } from '../services/api';
import styles from './EdgeHubBindingsPage.module.css';

const { Option } = Select;

// ── 类型 ──────────────────────────────────────────────────────────────────────

interface BindingItem {
  id:           string;
  storeId:      string;
  deviceId:     string;
  deviceCode:   string | undefined;
  deviceName:   string | undefined;
  deviceStatus: string | undefined;
  position:     string;
  employeeId:   string | null;
  channel:      number | null;
  status:       string;
  boundAt:      string | null;
  unboundAt:    string | null;
}

interface StoreOption {
  id: string;
  name: string;
  code: string;
}

// ── 常量 ──────────────────────────────────────────────────────────────────────

const POSITION_OPTIONS = [
  { value: 'store_manager',  label: '店长' },
  { value: 'front_manager',  label: '楼面经理' },
  { value: 'pass_runner',    label: '传菜员' },
  { value: 'kitchen_coord',  label: '厨房协调' },
  { value: 'cashier',        label: '收银员' },
  { value: 'waiter',         label: '服务员' },
];

const POSITION_LABEL: Record<string, string> = Object.fromEntries(
  POSITION_OPTIONS.map(o => [o.value, o.label])
);

// ── 主组件 ────────────────────────────────────────────────────────────────────

const EdgeHubBindingsPage: React.FC = () => {
  const [searchParams, setSearchParams] = useSearchParams();

  const [storeId,   setStoreId]   = useState(() => searchParams.get('store') ?? '');
  const [stores,    setStores]    = useState<StoreOption[]>([]);
  const [bindings,  setBindings]  = useState<BindingItem[]>([]);
  const [loading,   setLoading]   = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const [modalOpen,   setModalOpen]   = useState(false);
  const [editTarget,  setEditTarget]  = useState<BindingItem | null>(null);
  const [form] = Form.useForm();

  // 加载门店列表
  useEffect(() => {
    apiClient.get('/api/v1/stores?is_active=true')
      .then(resp => {
        const list: StoreOption[] = ((resp as any) ?? []).map((s: any) => ({
          id:   s.id,
          name: s.name,
          code: s.code,
        }));
        setStores(list);
        // 若 URL 中无 store 参数，默认选第一个
        if (!storeId && list.length > 0) setStoreId(list[0].id);
      })
      .catch(() => {/* silent — bindings page still usable without store list */});
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // 门店切换 → 同步 URL
  useEffect(() => {
    if (storeId) setSearchParams({ store: storeId }, { replace: true });
  }, [storeId, setSearchParams]);

  const fetchBindings = async () => {
    setLoading(true);
    try {
      const resp = await apiClient.get(`/api/v1/edge-hub/bindings/${storeId}`);
      setBindings(((resp as any).data?.bindings) ?? []);
    } catch (err) {
      handleApiError(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchBindings(); }, [storeId]);

  const openCreate = () => {
    setEditTarget(null);
    form.resetFields();
    setModalOpen(true);
  };

  const openEdit = (row: BindingItem) => {
    setEditTarget(row);
    form.setFieldsValue({
      deviceId:   row.deviceId,
      position:   row.position,
      employeeId: row.employeeId ?? '',
      channel:    row.channel,
    });
    setModalOpen(true);
  };

  const handleSubmit = async () => {
    const values = await form.validateFields();
    setSubmitting(true);
    try {
      if (editTarget) {
        await apiClient.put(`/api/v1/edge-hub/bindings/item/${editTarget.id}`, values);
        message.success('绑定已更新');
      } else {
        await apiClient.post(`/api/v1/edge-hub/bindings/${storeId}`, values);
        message.success('绑定已创建');
      }
      setModalOpen(false);
      await fetchBindings();
    } catch (err) {
      handleApiError(err);
    } finally {
      setSubmitting(false);
    }
  };

  const handleUnbind = async (bindingId: string) => {
    try {
      await apiClient.delete(`/api/v1/edge-hub/bindings/item/${bindingId}`);
      message.success('已解除绑定');
      await fetchBindings();
    } catch (err) {
      handleApiError(err);
    }
  };

  const columns = [
    {
      title: '岗位', dataIndex: 'position', width: 110,
      render: (v: string) => <Tag color="blue">{POSITION_LABEL[v] ?? v}</Tag>,
    },
    {
      title: '耳机设备', key: 'device', width: 180,
      render: (_: unknown, r: BindingItem) => (
        <span>
          <code>{r.deviceCode ?? r.deviceId}</code>
          {r.deviceName && <span className={styles.deviceName}>{r.deviceName}</span>}
        </span>
      ),
    },
    {
      title: '设备状态', dataIndex: 'deviceStatus', width: 90,
      render: (v: string | undefined) => v ? (
        <Badge
          color={v === 'online' ? '#1A7A52' : '#C53030'}
          text={v === 'online' ? '在线' : '离线'}
        />
      ) : '—',
    },
    {
      title: '频道', dataIndex: 'channel', width: 70,
      render: (v: number | null) => v ?? '—',
    },
    {
      title: '员工ID', dataIndex: 'employeeId', width: 100,
      render: (v: string | null) => v ?? '—',
    },
    {
      title: '绑定状态', dataIndex: 'status', width: 90,
      render: (v: string) => (
        <Tag color={v === 'active' ? 'green' : 'default'}>
          {v === 'active' ? '已绑定' : '已解绑'}
        </Tag>
      ),
    },
    {
      title: '绑定时间', dataIndex: 'boundAt', width: 140,
      render: (v: string | null) => v ? dayjs(v).format('MM-DD HH:mm') : '—',
    },
    {
      title: '操作', key: 'actions', width: 100,
      render: (_: unknown, r: BindingItem) => (
        <Space size={4}>
          <Button
            type="link" size="small" icon={<EditOutlined />}
            onClick={() => openEdit(r)}
          />
          {r.status === 'active' && (
            <Popconfirm
              title="确认解除此绑定？"
              onConfirm={() => handleUnbind(r.id)}
              okText="解绑" cancelText="取消"
            >
              <Button type="link" size="small" danger icon={<DeleteOutlined />} />
            </Popconfirm>
          )}
        </Space>
      ),
    },
  ];

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <h2 className={styles.title}>岗位与耳机绑定管理</h2>
        <Space>
          <Select
            value={storeId || undefined}
            onChange={setStoreId}
            style={{ width: 160 }}
            placeholder="选择门店"
            showSearch
            optionFilterProp="label"
            options={stores.map(s => ({
              value: s.id,
              label: `${s.code} ${s.name}`,
            }))}
          />
          <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
            新建绑定
          </Button>
        </Space>
      </div>

      <Spin spinning={loading}>
        <Card size="small" className={styles.tableCard}>
          {bindings.length === 0 && !loading ? (
            <Empty description="暂无绑定记录，请点击「新建绑定」" />
          ) : (
            <Table
              dataSource={bindings}
              columns={columns}
              rowKey="id"
              size="small"
              pagination={{ pageSize: 20, size: 'small' }}
              rowClassName={(r) => r.status === 'inactive' ? styles.inactiveRow : ''}
            />
          )}
        </Card>
      </Spin>

      {/* 新建 / 编辑弹窗 */}
      <Modal
        title={editTarget ? '编辑绑定' : '新建绑定'}
        open={modalOpen}
        onOk={handleSubmit}
        onCancel={() => setModalOpen(false)}
        confirmLoading={submitting}
        okText={editTarget ? '保存' : '创建'}
        destroyOnClose
      >
        <Form form={form} layout="vertical">
          {!editTarget && (
            <Form.Item name="deviceId" label="耳机设备ID" rules={[{ required: true }]}>
              <Input placeholder="输入设备 ID" />
            </Form.Item>
          )}
          <Form.Item name="position" label="绑定岗位" rules={[{ required: true }]}>
            <Select placeholder="选择岗位">
              {POSITION_OPTIONS.map(o => (
                <Option key={o.value} value={o.value}>{o.label}</Option>
              )) : null}
            </Select>
          </Form.Item>
          <Form.Item name="employeeId" label="员工ID（可选）">
            <Input placeholder="留空表示未指定员工" />
          </Form.Item>
          <Form.Item name="channel" label="通话频道（可选）">
            <InputNumber min={1} max={99} style={{ width: '100%' }} placeholder="1-99" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default EdgeHubBindingsPage;
