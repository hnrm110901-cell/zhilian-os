import React, { useState, useCallback, useEffect } from 'react';
import { Card, Table, Button, Modal, Form, Input, Select, Tag, Space, Avatar } from 'antd';
import { PlusOutlined, EditOutlined, DeleteOutlined, UserOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { apiClient } from '../services/api';
import { handleApiError, showSuccess } from '../utils/message';

const { Option } = Select;

const roleColor: Record<string, string> = { manager: 'blue', chef: 'orange', waiter: 'green', cashier: 'purple' };
const roleLabel: Record<string, string> = { manager: '经理', chef: '厨师', waiter: '服务员', cashier: '收银员' };

const EmployeeManagementPage: React.FC = () => {
  const [employees, setEmployees] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalVisible, setModalVisible] = useState(false);
  const [editingEmployee, setEditingEmployee] = useState<any>(null);
  const [form] = Form.useForm();

  const loadEmployees = useCallback(async () => {
    setLoading(true);
    try {
      const res = await apiClient.get('/employees');
      setEmployees(res.data?.employees || res.data || []);
    } catch (err: any) {
      handleApiError(err, '加载员工列表失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadEmployees(); }, [loadEmployees]);

  const openModal = (employee?: any) => {
    setEditingEmployee(employee || null);
    form.setFieldsValue(employee || {});
    setModalVisible(true);
  };

  const saveEmployee = async (values: any) => {
    try {
      if (editingEmployee) {
        await apiClient.patch(`/employees/${editingEmployee.employee_id || editingEmployee.id}`, values);
        showSuccess('员工信息更新成功');
      } else {
        await apiClient.post('/employees', values);
        showSuccess('员工创建成功');
      }
      setModalVisible(false);
      form.resetFields();
      loadEmployees();
    } catch (err: any) {
      handleApiError(err, '保存失败');
    }
  };

  const deleteEmployee = async (employee: any) => {
    try {
      await apiClient.delete(`/employees/${employee.employee_id || employee.id}`);
      showSuccess('员工已删除');
      loadEmployees();
    } catch (err: any) {
      handleApiError(err, '删除失败');
    }
  };

  const columns: ColumnsType<any> = [
    {
      title: '员工', key: 'name',
      render: (_: any, record: any) => (
        <Space>
          <Avatar icon={<UserOutlined />} style={{ backgroundColor: '#1890ff' }} />
          <div>
            <div style={{ fontWeight: 500 }}>{record.name}</div>
            <div style={{ fontSize: 12, color: '#999' }}>{record.employee_id || record.id}</div>
          </div>
        </Space>
      ),
    },
    {
      title: '角色', dataIndex: 'role', key: 'role',
      render: (v: string) => <Tag color={roleColor[v] || 'default'}>{roleLabel[v] || v || '-'}</Tag>,
    },
    { title: '门店', dataIndex: 'store_id', key: 'store' },
    { title: '联系方式', dataIndex: 'phone', key: 'phone', render: (v: string) => v || '-' },
    { title: '入职日期', dataIndex: 'hire_date', key: 'hire_date', render: (v: string) => v || '-' },
    {
      title: '状态', dataIndex: 'status', key: 'status',
      render: (v: string) => <Tag color={v === 'active' ? 'green' : 'red'}>{v === 'active' ? '在职' : '离职'}</Tag>,
    },
    {
      title: '操作', key: 'action',
      render: (_: any, record: any) => (
        <Space>
          <Button size="small" icon={<EditOutlined />} onClick={() => openModal(record)}>编辑</Button>
          <Button size="small" danger icon={<DeleteOutlined />} onClick={() => deleteEmployee(record)}>删除</Button>
        </Space>
      ),
    },
  ];

  return (
    <div>
      <Card
        title="员工管理"
        extra={<Button type="primary" icon={<PlusOutlined />} onClick={() => openModal()}>新增员工</Button>}
      >
        <Table columns={columns} dataSource={employees} rowKey={(r, i) => r.employee_id || r.id || String(i)} loading={loading} />
      </Card>

      <Modal
        title={editingEmployee ? '编辑员工' : '新增员工'}
        open={modalVisible}
        onCancel={() => { setModalVisible(false); form.resetFields(); }}
        onOk={() => form.submit()}
        okText="保存"
      >
        <Form form={form} layout="vertical" onFinish={saveEmployee}>
          <Form.Item name="name" label="姓名" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="role" label="角色" rules={[{ required: true }]}>
            <Select>
              <Option value="manager">经理</Option>
              <Option value="chef">厨师</Option>
              <Option value="waiter">服务员</Option>
              <Option value="cashier">收银员</Option>
            </Select>
          </Form.Item>
          <Form.Item name="store_id" label="门店">
            <Select>
              <Option value="STORE001">门店001</Option>
              <Option value="STORE002">门店002</Option>
            </Select>
          </Form.Item>
          <Form.Item name="phone" label="联系方式"><Input /></Form.Item>
          <Form.Item name="hire_date" label="入职日期"><Input type="date" /></Form.Item>
          <Form.Item name="status" label="状态" initialValue="active">
            <Select><Option value="active">在职</Option><Option value="inactive">离职</Option></Select>
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default EmployeeManagementPage;
