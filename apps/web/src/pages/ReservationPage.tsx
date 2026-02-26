import React, { useState, useCallback, useEffect } from 'react';
import {
  Card, Col, Row, Select, DatePicker, Tabs, Statistic, Table, Tag, Space,
  Button, Form, Input, InputNumber, Modal, Descriptions, Badge, TimePicker,
  Popconfirm, Alert,
} from 'antd';
import {
  PlusOutlined, ReloadOutlined, UserOutlined, PhoneOutlined,
  CalendarOutlined, CheckCircleOutlined, CloseCircleOutlined,
} from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import dayjs from 'dayjs';
import { apiClient } from '../services/api';
import { handleApiError, showSuccess } from '../utils/message';

const { Option } = Select;
const { TextArea } = Input;

const STATUS_COLOR: Record<string, string> = {
  pending: 'orange', confirmed: 'green', arrived: 'cyan',
  seated: 'blue', completed: 'default', cancelled: 'red', no_show: 'volcano',
};
const STATUS_LABEL: Record<string, string> = {
  pending: '待确认', confirmed: '已确认', arrived: '已到店',
  seated: '已入座', completed: '已完成', cancelled: '已取消', no_show: '未到店',
};
const TYPE_LABEL: Record<string, string> = {
  regular: '普通用餐', banquet: '宴会', private_room: '包厢',
};

const STORE_ID = 'STORE001';

const ReservationPage: React.FC = () => {
  const [reservations, setReservations] = useState<any[]>([]);
  const [overview, setOverview] = useState<any>(null);
  const [stats, setStats] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [createModal, setCreateModal] = useState(false);
  const [detailModal, setDetailModal] = useState(false);
  const [seatModal, setSeatModal] = useState(false);
  const [selected, setSelected] = useState<any>(null);
  const [filterDate, setFilterDate] = useState<string>(dayjs().format('YYYY-MM-DD'));
  const [filterStatus, setFilterStatus] = useState<string>('');
  const [filterType, setFilterType] = useState<string>('');
  const [submitting, setSubmitting] = useState(false);
  const [createForm] = Form.useForm();
  const [seatForm] = Form.useForm();
  const [reservationType, setReservationType] = useState('regular');

  const loadReservations = useCallback(async () => {
    setLoading(true);
    try {
      const params: any = { store_id: STORE_ID };
      if (filterDate) params.reservation_date = filterDate;
      if (filterStatus) params.status = filterStatus;
      if (filterType) params.reservation_type = filterType;
      const res = await apiClient.get('/api/v1/reservations', { params });
      setReservations(res.data || []);
    } catch (err: any) {
      handleApiError(err, '加载预约列表失败');
    } finally {
      setLoading(false);
    }
  }, [filterDate, filterStatus, filterType]);

  const loadOverview = useCallback(async () => {
    try {
      const res = await apiClient.get('/api/v1/reservations/today-overview', {
        params: { store_id: STORE_ID },
      });
      setOverview(res.data);
    } catch { /* 静默失败 */ }
  }, []);

  const loadStats = useCallback(async () => {
    try {
      const res = await apiClient.get('/api/v1/reservations/statistics', {
        params: { store_id: STORE_ID },
      });
      setStats(res.data);
    } catch { /* 静默失败 */ }
  }, []);

  useEffect(() => {
    loadReservations();
    loadOverview();
    loadStats();
  }, [loadReservations, loadOverview, loadStats]);

  const handleCreate = async (values: any) => {
    setSubmitting(true);
    try {
      const payload: any = {
        store_id: STORE_ID,
        customer_name: values.customer_name,
        customer_phone: values.customer_phone,
        customer_email: values.customer_email,
        party_size: values.party_size,
        reservation_date: values.reservation_date.format('YYYY-MM-DD'),
        reservation_time: values.reservation_time.format('HH:mm:ss'),
        reservation_type: values.reservation_type || 'regular',
        special_requests: values.special_requests,
        dietary_restrictions: values.dietary_restrictions,
        notes: values.notes,
      };
      if (values.reservation_type === 'banquet' || values.reservation_type === 'private_room') {
        payload.room_name = values.room_name;
        payload.estimated_budget = values.estimated_budget ? values.estimated_budget * 100 : undefined;
        payload.banquet_details = {
          menu_preference: values.menu_preference,
          decoration: values.decoration,
        };
      }
      await apiClient.post('/api/v1/reservations', payload);
      showSuccess('预约创建成功');
      setCreateModal(false);
      createForm.resetFields();
      loadReservations();
      loadOverview();
    } catch (err: any) {
      handleApiError(err, '创建预约失败');
    } finally {
      setSubmitting(false);
    }
  };

  const handleConfirm = async (id: string) => {
    try {
      await apiClient.patch(`/api/v1/reservations/${id}`, { status: 'confirmed' });
      showSuccess('已确认');
      loadReservations(); loadOverview();
    } catch (err: any) { handleApiError(err, '确认失败'); }
  };

  const handleCheckin = async (id: string) => {
    try {
      await apiClient.post(`/api/v1/reservations/${id}/checkin`);
      showSuccess('签到成功');
      loadReservations(); loadOverview();
    } catch (err: any) { handleApiError(err, '签到失败'); }
  };

  const handleSeat = async (values: any) => {
    try {
      await apiClient.post(`/api/v1/reservations/${selected.id}/seat`, {
        table_number: values.table_number,
      });
      showSuccess(`已分配桌位 ${values.table_number}`);
      setSeatModal(false);
      seatForm.resetFields();
      loadReservations(); loadOverview();
    } catch (err: any) { handleApiError(err, '分配桌位失败'); }
  };

  const handleNoShow = async (id: string) => {
    try {
      await apiClient.post(`/api/v1/reservations/${id}/no-show`);
      showSuccess('已标记未到店');
      loadReservations(); loadOverview();
    } catch (err: any) { handleApiError(err, '操作失败'); }
  };

  const handleCancel = async (id: string) => {
    try {
      await apiClient.patch(`/api/v1/reservations/${id}`, { status: 'cancelled' });
      showSuccess('已取消');
      loadReservations(); loadOverview();
    } catch (err: any) { handleApiError(err, '取消失败'); }
  };

  const handleComplete = async (id: string) => {
    try {
      await apiClient.post(`/api/v1/reservations/${id}/complete`);
      showSuccess('已完成');
      loadReservations(); loadOverview();
    } catch (err: any) { handleApiError(err, '操作失败'); }
  };

  const columns: ColumnsType<any> = [
    { title: '预约ID', dataIndex: 'id', key: 'id', width: 200, ellipsis: true },
    {
      title: '客户', key: 'customer',
      render: (_: any, r: any) => (
        <div>
          <div><UserOutlined /> {r.customer_name}</div>
          <div style={{ color: '#999', fontSize: 12 }}><PhoneOutlined /> {r.customer_phone}</div>
        </div>
      ),
    },
    { title: '人数', dataIndex: 'party_size', key: 'party_size', width: 60, render: (v: number) => `${v}人` },
    {
      title: '日期时间', key: 'datetime',
      render: (_: any, r: any) => (
        <div>
          <div><CalendarOutlined /> {r.reservation_date}</div>
          <div style={{ color: '#666', fontSize: 12 }}>{r.reservation_time?.slice(0, 5)}</div>
        </div>
      ),
    },
    {
      title: '类型', dataIndex: 'reservation_type', key: 'reservation_type', width: 80,
      render: (v: string) => <Tag>{TYPE_LABEL[v] || v}</Tag>,
    },
    {
      title: '桌位', key: 'table', width: 80,
      render: (_: any, r: any) => r.table_number || r.room_name || <span style={{ color: '#ccc' }}>未分配</span>,
    },
    {
      title: '状态', dataIndex: 'status', key: 'status', width: 90,
      render: (v: string) => <Tag color={STATUS_COLOR[v]}>{STATUS_LABEL[v] || v}</Tag>,
    },
    {
      title: '操作', key: 'actions', width: 220,
      render: (_: any, r: any) => (
        <Space size={4} wrap>
          <Button size="small" type="link" onClick={() => { setSelected(r); setDetailModal(true); }}>详情</Button>
          {r.status === 'pending' && (
            <Button size="small" type="link" onClick={() => handleConfirm(r.id)}>确认</Button>
          )}
          {(r.status === 'pending' || r.status === 'confirmed') && (
            <Button size="small" type="link" icon={<CheckCircleOutlined />} onClick={() => handleCheckin(r.id)}>签到</Button>
          )}
          {r.status === 'arrived' && (
            <Button size="small" type="primary" ghost onClick={() => { setSelected(r); setSeatModal(true); }}>入座</Button>
          )}
          {r.status === 'seated' && (
            <Button size="small" type="link" onClick={() => handleComplete(r.id)}>完成</Button>
          )}
          {(r.status === 'pending' || r.status === 'confirmed') && (
            <Popconfirm title="标记未到店？" onConfirm={() => handleNoShow(r.id)}>
              <Button size="small" type="link" danger>未到店</Button>
            </Popconfirm>
          )}
          {(r.status === 'pending' || r.status === 'confirmed') && (
            <Popconfirm title="确认取消？" onConfirm={() => handleCancel(r.id)}>
              <Button size="small" danger type="link"><CloseCircleOutlined /></Button>
            </Popconfirm>
          )}
        </Space>
      ),
    },
  ];

  const overviewTab = (
    <div>
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={4}><Card size="small"><Statistic title="今日总预约" value={overview?.total ?? '--'} /></Card></Col>
        <Col span={4}><Card size="small"><Statistic title="待确认" value={overview?.pending_count ?? '--'} valueStyle={{ color: '#fa8c16' }} /></Card></Col>
        <Col span={4}><Card size="small"><Statistic title="已确认" value={overview?.confirmed_count ?? '--'} valueStyle={{ color: '#52c41a' }} /></Card></Col>
        <Col span={4}><Card size="small"><Statistic title="已入座" value={overview?.seated_count ?? '--'} valueStyle={{ color: '#1890ff' }} /></Card></Col>
        <Col span={4}><Card size="small"><Statistic title="未到店" value={overview?.no_show_count ?? '--'} valueStyle={{ color: '#ff4d4f' }} /></Card></Col>
        <Col span={4}><Card size="small"><Statistic title="今日总人数" value={overview?.total_guests ?? '--'} suffix="人" /></Card></Col>
      </Row>
      {(overview?.upcoming_soon?.length > 0) && (
        <Alert
          type="warning"
          showIcon
          message={`${overview.upcoming_soon.length} 个预约将在2小时内到店`}
          description={overview.upcoming_soon.map((r: any) => `${r.customer_name}（${r.reservation_time?.slice(0, 5)}，${r.party_size}人）`).join('　')}
          style={{ marginBottom: 16 }}
        />
      )}
    </div>
  );

  const statsTab = stats && (
    <Row gutter={16}>
      <Col span={6}><Card size="small"><Statistic title="总预约数" value={stats.total} /></Card></Col>
      <Col span={6}><Card size="small"><Statistic title="总接待人数" value={stats.total_guests} suffix="人" /></Card></Col>
      <Col span={6}><Card size="small"><Statistic title="平均桌均人数" value={stats.avg_party_size} /></Card></Col>
      <Col span={6}><Card size="small"><Statistic title="取消率" value={(stats.cancellation_rate * 100).toFixed(1)} suffix="%" valueStyle={{ color: '#ff4d4f' }} /></Card></Col>
      <Col span={6} style={{ marginTop: 12 }}><Card size="small"><Statistic title="确认率" value={(stats.confirmed_rate * 100).toFixed(1)} suffix="%" valueStyle={{ color: '#52c41a' }} /></Card></Col>
      <Col span={6} style={{ marginTop: 12 }}><Card size="small"><Statistic title="未到店率" value={(stats.no_show_rate * 100).toFixed(1)} suffix="%" valueStyle={{ color: '#fa8c16' }} /></Card></Col>
      <Col span={6} style={{ marginTop: 12 }}><Card size="small"><Statistic title="宴会预约" value={stats.by_type?.banquet ?? 0} /></Card></Col>
      <Col span={6} style={{ marginTop: 12 }}><Card size="small"><Statistic title="包厢预约" value={stats.by_type?.private_room ?? 0} /></Card></Col>
    </Row>
  );

  const tabItems = [
    {
      key: 'overview', label: '今日概览',
      children: (
        <div>
          {overviewTab}
          <Card
            title="今日预约列表"
            extra={
              <Space>
                <Button icon={<ReloadOutlined />} onClick={() => { loadReservations(); loadOverview(); }}>刷新</Button>
                <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateModal(true)}>新建预约</Button>
              </Space>
            }
          >
            <Table columns={columns} dataSource={reservations} rowKey="id" loading={loading} size="small" pagination={{ pageSize: 15 }} />
          </Card>
        </div>
      ),
    },
    {
      key: 'list', label: '全部预约',
      children: (
        <Card
          title="预约列表"
          extra={
            <Space wrap>
              <DatePicker
                defaultValue={dayjs()}
                onChange={(_, ds) => setFilterDate(ds as string)}
                allowClear
                placeholder="按日期筛选"
              />
              <Select value={filterStatus} onChange={setFilterStatus} style={{ width: 110 }} allowClear placeholder="状态">
                {Object.entries(STATUS_LABEL).map(([k, v]) => <Option key={k} value={k}>{v}</Option>)}
              </Select>
              <Select value={filterType} onChange={setFilterType} style={{ width: 110 }} allowClear placeholder="类型">
                {Object.entries(TYPE_LABEL).map(([k, v]) => <Option key={k} value={k}>{v}</Option>)}
              </Select>
              <Button icon={<ReloadOutlined />} onClick={loadReservations}>查询</Button>
              <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateModal(true)}>新建预约</Button>
            </Space>
          }
        >
          <Table columns={columns} dataSource={reservations} rowKey="id" loading={loading} size="small" pagination={{ pageSize: 20 }} />
        </Card>
      ),
    },
    {
      key: 'stats', label: '统计分析',
      children: <Card title="近30天统计">{statsTab || <Card loading />}</Card>,
    },
  ];

  return (
    <div>
      <Tabs items={tabItems} />

      {/* 新建预约 Modal */}
      <Modal
        title="新建预约"
        open={createModal}
        onCancel={() => { setCreateModal(false); createForm.resetFields(); }}
        onOk={() => createForm.submit()}
        okText="创建"
        confirmLoading={submitting}
        width={600}
      >
        <Form form={createForm} layout="vertical" onFinish={handleCreate}>
          <Row gutter={12}>
            <Col span={12}>
              <Form.Item name="customer_name" label="客户姓名" rules={[{ required: true }]}>
                <Input prefix={<UserOutlined />} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="customer_phone" label="联系电话" rules={[{ required: true }, { pattern: /^1[3-9]\d{9}$/, message: '手机号格式不正确' }]}>
                <Input prefix={<PhoneOutlined />} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="customer_email" label="邮箱"><Input /></Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="party_size" label="用餐人数" rules={[{ required: true }]}>
                <InputNumber min={1} max={500} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="reservation_date" label="预约日期" rules={[{ required: true }]}>
                <DatePicker style={{ width: '100%' }} disabledDate={(d) => d && d < dayjs().startOf('day')} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="reservation_time" label="预约时间" rules={[{ required: true }]}>
                <TimePicker format="HH:mm" minuteStep={30} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="reservation_type" label="预约类型" initialValue="regular">
                <Select onChange={setReservationType}>
                  <Option value="regular">普通用餐</Option>
                  <Option value="banquet">宴会</Option>
                  <Option value="private_room">包厢</Option>
                </Select>
              </Form.Item>
            </Col>
            {(reservationType === 'banquet' || reservationType === 'private_room') && (
              <>
                <Col span={12}>
                  <Form.Item name="room_name" label="包厢/宴会厅名称"><Input /></Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item name="estimated_budget" label="预估预算（元）">
                    <InputNumber min={0} style={{ width: '100%' }} />
                  </Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item name="menu_preference" label="菜单偏好"><Input placeholder="如：粤菜、海鲜为主" /></Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item name="decoration" label="布置要求"><Input placeholder="如：生日布置、婚宴布置" /></Form.Item>
                </Col>
              </>
            )}
            <Col span={24}>
              <Form.Item name="dietary_restrictions" label="饮食禁忌"><Input placeholder="如：不吃辣、素食、过敏食材" /></Form.Item>
            </Col>
            <Col span={24}>
              <Form.Item name="special_requests" label="特殊要求"><TextArea rows={2} /></Form.Item>
            </Col>
            <Col span={24}>
              <Form.Item name="notes" label="备注"><TextArea rows={2} /></Form.Item>
            </Col>
          </Row>
        </Form>
      </Modal>

      {/* 详情 Modal */}
      <Modal
        title="预约详情"
        open={detailModal}
        onCancel={() => setDetailModal(false)}
        footer={<Button onClick={() => setDetailModal(false)}>关闭</Button>}
        width={600}
      >
        {selected && (
          <Descriptions column={2} bordered size="small">
            <Descriptions.Item label="预约ID" span={2}>{selected.id}</Descriptions.Item>
            <Descriptions.Item label="客户姓名">{selected.customer_name}</Descriptions.Item>
            <Descriptions.Item label="联系电话">{selected.customer_phone}</Descriptions.Item>
            <Descriptions.Item label="邮箱">{selected.customer_email || '-'}</Descriptions.Item>
            <Descriptions.Item label="用餐人数">{selected.party_size}人</Descriptions.Item>
            <Descriptions.Item label="预约日期">{selected.reservation_date}</Descriptions.Item>
            <Descriptions.Item label="预约时间">{selected.reservation_time?.slice(0, 5)}</Descriptions.Item>
            <Descriptions.Item label="类型"><Tag>{TYPE_LABEL[selected.reservation_type] || selected.reservation_type}</Tag></Descriptions.Item>
            <Descriptions.Item label="状态"><Tag color={STATUS_COLOR[selected.status]}>{STATUS_LABEL[selected.status]}</Tag></Descriptions.Item>
            <Descriptions.Item label="桌位/包厢">{selected.table_number || selected.room_name || '-'}</Descriptions.Item>
            <Descriptions.Item label="到店时间">{selected.arrival_time ? selected.arrival_time.slice(0, 16) : '-'}</Descriptions.Item>
            {selected.estimated_budget && (
              <Descriptions.Item label="预估预算">¥{(selected.estimated_budget / 100).toFixed(0)}</Descriptions.Item>
            )}
            <Descriptions.Item label="饮食禁忌" span={2}>{selected.dietary_restrictions || '-'}</Descriptions.Item>
            <Descriptions.Item label="特殊要求" span={2}>{selected.special_requests || '-'}</Descriptions.Item>
            {selected.banquet_details && Object.keys(selected.banquet_details).length > 0 && (
              <Descriptions.Item label="宴会详情" span={2}>
                {Object.entries(selected.banquet_details).map(([k, v]) => (
                  <div key={k}><b>{k}：</b>{String(v)}</div>
                ))}
              </Descriptions.Item>
            )}
            <Descriptions.Item label="备注" span={2}>{selected.notes || '-'}</Descriptions.Item>
            <Descriptions.Item label="创建时间" span={2}>{selected.created_at?.slice(0, 16)}</Descriptions.Item>
          </Descriptions>
        )}
      </Modal>

      {/* 分配桌位 Modal */}
      <Modal
        title="分配桌位并入座"
        open={seatModal}
        onCancel={() => setSeatModal(false)}
        onOk={() => seatForm.submit()}
        okText="确认入座"
      >
        <Form form={seatForm} layout="vertical" onFinish={handleSeat}>
          <Form.Item name="table_number" label="桌位号" rules={[{ required: true, message: '请输入桌位号' }]}>
            <Input placeholder="如：A01、VIP包厢1" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default ReservationPage;
