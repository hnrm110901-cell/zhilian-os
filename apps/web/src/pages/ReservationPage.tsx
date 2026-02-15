import React, { useState } from 'react';
import {
  Card,
  Form,
  Input,
  Button,
  DatePicker,
  InputNumber,
  Select,
  Table,
  message,
  Space,
  Tag,
  Tabs,
  Modal,
} from 'antd';
import { CalendarOutlined, UserOutlined, PhoneOutlined } from '@ant-design/icons';
import { apiClient } from '../services/api';
import type { ReservationRequest } from '../types/api';
import dayjs from 'dayjs';

const { TextArea } = Input;
const { TabPane } = Tabs;

const ReservationPage: React.FC = () => {
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(false);
  const [reservations, setReservations] = useState<any[]>([]);
  const [selectedReservation, setSelectedReservation] = useState<any>(null);
  const [modalVisible, setModalVisible] = useState(false);

  // 创建预定
  const handleCreate = async (values: any) => {
    try {
      setLoading(true);

      const request: ReservationRequest = {
        action: 'create',
        reservation_data: {
          customer_name: values.customer_name,
          customer_phone: values.customer_phone,
          party_size: values.party_size,
          reservation_date: values.reservation_date.format('YYYY-MM-DD'),
          reservation_time: values.reservation_time,
          special_requests: values.special_requests,
        },
      };

      const response = await apiClient.callAgent('reservation', request);

      if (response.output_data.success) {
        message.success('预定创建成功');
        form.resetFields();
        // 添加到列表
        setReservations([
          {
            ...response.output_data.reservation,
            key: response.output_data.reservation_id,
          },
          ...reservations,
        ]);
      } else {
        message.error(response.output_data.error || '预定创建失败');
      }
    } catch (error: any) {
      message.error(error.message || '预定创建失败');
    } finally {
      setLoading(false);
    }
  };

  // 查看预定详情
  const handleViewDetails = (record: any) => {
    setSelectedReservation(record);
    setModalVisible(true);
  };

  // 确认预定
  const handleConfirm = async (reservationId: string) => {
    try {
      const request: ReservationRequest = {
        action: 'confirm',
        reservation_id: reservationId,
      };

      const response = await apiClient.callAgent('reservation', request);

      if (response.output_data.success) {
        message.success('预定已确认');
        // 更新列表
        setReservations(
          reservations.map((r) =>
            r.reservation_id === reservationId ? { ...r, status: 'confirmed' } : r
          )
        );
      } else {
        message.error(response.output_data.error || '确认失败');
      }
    } catch (error: any) {
      message.error(error.message || '确认失败');
    }
  };

  // 取消预定
  const handleCancel = async (reservationId: string) => {
    Modal.confirm({
      title: '确认取消预定',
      content: '确定要取消这个预定吗？',
      onOk: async () => {
        try {
          const request: ReservationRequest = {
            action: 'cancel',
            reservation_id: reservationId,
            reason: '客户取消',
          };

          const response = await apiClient.callAgent('reservation', request);

          if (response.output_data.success) {
            message.success('预定已取消');
            // 更新列表
            setReservations(
              reservations.map((r) =>
                r.reservation_id === reservationId ? { ...r, status: 'cancelled' } : r
              )
            );
          } else {
            message.error(response.output_data.error || '取消失败');
          }
        } catch (error: any) {
          message.error(error.message || '取消失败');
        }
      },
    });
  };

  const columns = [
    {
      title: '预定ID',
      dataIndex: 'reservation_id',
      key: 'reservation_id',
      width: 180,
    },
    {
      title: '客户姓名',
      dataIndex: 'customer_name',
      key: 'customer_name',
      render: (text: string) => (
        <Space>
          <UserOutlined />
          {text}
        </Space>
      ),
    },
    {
      title: '联系电话',
      dataIndex: 'customer_phone',
      key: 'customer_phone',
      render: (text: string) => (
        <Space>
          <PhoneOutlined />
          {text}
        </Space>
      ),
    },
    {
      title: '人数',
      dataIndex: 'party_size',
      key: 'party_size',
      width: 80,
    },
    {
      title: '预定日期',
      dataIndex: 'reservation_date',
      key: 'reservation_date',
      render: (text: string) => (
        <Space>
          <CalendarOutlined />
          {text}
        </Space>
      ),
    },
    {
      title: '预定时间',
      dataIndex: 'reservation_time',
      key: 'reservation_time',
      width: 100,
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (status: string) => {
        const colorMap: Record<string, string> = {
          pending: 'orange',
          confirmed: 'green',
          seated: 'blue',
          completed: 'default',
          cancelled: 'red',
          no_show: 'red',
        };
        const textMap: Record<string, string> = {
          pending: '待确认',
          confirmed: '已确认',
          seated: '已入座',
          completed: '已完成',
          cancelled: '已取消',
          no_show: '未到店',
        };
        return <Tag color={colorMap[status]}>{textMap[status] || status}</Tag>;
      },
    },
    {
      title: '操作',
      key: 'action',
      width: 200,
      render: (_: any, record: any) => (
        <Space>
          <Button type="link" size="small" onClick={() => handleViewDetails(record)}>
            详情
          </Button>
          {record.status === 'pending' && (
            <>
              <Button
                type="link"
                size="small"
                onClick={() => handleConfirm(record.reservation_id)}
              >
                确认
              </Button>
              <Button
                type="link"
                danger
                size="small"
                onClick={() => handleCancel(record.reservation_id)}
              >
                取消
              </Button>
            </>
          )}
        </Space>
      ),
    },
  ];

  return (
    <div>
      <h1 style={{ marginBottom: 24 }}>预定宴会Agent</h1>

      <Tabs defaultActiveKey="create">
        <TabPane tab="创建预定" key="create">
          <Card>
            <Form form={form} layout="vertical" onFinish={handleCreate}>
              <Form.Item
                label="客户姓名"
                name="customer_name"
                rules={[{ required: true, message: '请输入客户姓名' }]}
              >
                <Input prefix={<UserOutlined />} placeholder="请输入客户姓名" />
              </Form.Item>

              <Form.Item
                label="联系电话"
                name="customer_phone"
                rules={[
                  { required: true, message: '请输入联系电话' },
                  { pattern: /^1[3-9]\d{9}$/, message: '请输入有效的手机号码' },
                ]}
              >
                <Input prefix={<PhoneOutlined />} placeholder="请输入11位手机号" />
              </Form.Item>

              <Form.Item
                label="用餐人数"
                name="party_size"
                rules={[{ required: true, message: '请输入用餐人数' }]}
              >
                <InputNumber min={1} max={100} style={{ width: '100%' }} />
              </Form.Item>

              <Form.Item
                label="预定日期"
                name="reservation_date"
                rules={[{ required: true, message: '请选择预定日期' }]}
              >
                <DatePicker
                  style={{ width: '100%' }}
                  disabledDate={(current) => {
                    return current && current < dayjs().startOf('day');
                  }}
                />
              </Form.Item>

              <Form.Item
                label="预定时间"
                name="reservation_time"
                rules={[{ required: true, message: '请选择预定时间' }]}
              >
                <Select placeholder="请选择预定时间">
                  <Select.Option value="11:00">11:00</Select.Option>
                  <Select.Option value="11:30">11:30</Select.Option>
                  <Select.Option value="12:00">12:00</Select.Option>
                  <Select.Option value="12:30">12:30</Select.Option>
                  <Select.Option value="17:00">17:00</Select.Option>
                  <Select.Option value="17:30">17:30</Select.Option>
                  <Select.Option value="18:00">18:00</Select.Option>
                  <Select.Option value="18:30">18:30</Select.Option>
                  <Select.Option value="19:00">19:00</Select.Option>
                  <Select.Option value="19:30">19:30</Select.Option>
                </Select>
              </Form.Item>

              <Form.Item label="特殊要求" name="special_requests">
                <TextArea rows={3} placeholder="请输入特殊要求（可选）" />
              </Form.Item>

              <Form.Item>
                <Space>
                  <Button type="primary" htmlType="submit" loading={loading}>
                    创建预定
                  </Button>
                  <Button onClick={() => form.resetFields()}>重置</Button>
                </Space>
              </Form.Item>
            </Form>
          </Card>
        </TabPane>

        <TabPane tab="预定列表" key="list">
          <Card>
            <Table
              dataSource={reservations}
              columns={columns}
              pagination={{ pageSize: 10 }}
              locale={{ emptyText: '暂无预定记录' }}
            />
          </Card>
        </TabPane>
      </Tabs>

      {/* 预定详情Modal */}
      <Modal
        title="预定详情"
        open={modalVisible}
        onCancel={() => setModalVisible(false)}
        footer={[
          <Button key="close" onClick={() => setModalVisible(false)}>
            关闭
          </Button>,
        ]}
        width={600}
      >
        {selectedReservation && (
          <div>
            <p>
              <strong>预定ID:</strong> {selectedReservation.reservation_id}
            </p>
            <p>
              <strong>客户姓名:</strong> {selectedReservation.customer_name}
            </p>
            <p>
              <strong>联系电话:</strong> {selectedReservation.customer_phone}
            </p>
            <p>
              <strong>用餐人数:</strong> {selectedReservation.party_size}人
            </p>
            <p>
              <strong>预定日期:</strong> {selectedReservation.reservation_date}
            </p>
            <p>
              <strong>预定时间:</strong> {selectedReservation.reservation_time}
            </p>
            <p>
              <strong>状态:</strong>{' '}
              <Tag
                color={
                  selectedReservation.status === 'confirmed'
                    ? 'green'
                    : selectedReservation.status === 'pending'
                    ? 'orange'
                    : 'red'
                }
              >
                {selectedReservation.status}
              </Tag>
            </p>
            {selectedReservation.special_requests && (
              <p>
                <strong>特殊要求:</strong> {selectedReservation.special_requests}
              </p>
            )}
            <p>
              <strong>创建时间:</strong> {selectedReservation.created_at}
            </p>
          </div>
        )}
      </Modal>
    </div>
  );
};

export default ReservationPage;
