import React, { useState, useEffect, useCallback } from 'react';
import { Card, Table, Button, Modal, Form, Input, Select, message, Space, Tag, Avatar } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { PlusOutlined, EditOutlined, DeleteOutlined, UserOutlined, ReloadOutlined } from '@ant-design/icons';
import { usePermission } from '../hooks/usePermission';
import { useNavigate } from 'react-router-dom';
import apiClient from '../services/api';
import { handleApiError, showSuccess } from '../utils/message';

const { Option } = Select;

interface User {
  id: string;
  username: string;
  email: string;
  role: 'admin' | 'manager' | 'staff';
  avatar?: string;
  status: 'active' | 'inactive';
  createdAt: string;
}

const UserManagementPage: React.FC = () => {
  const [users, setUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [isModalVisible, setIsModalVisible] = useState(false);
  const [editingUser, setEditingUser] = useState<User | null>(null);
  const [form] = Form.useForm();
  const { isAdmin } = usePermission();
  const navigate = useNavigate();

  useEffect(() => {
    if (!isAdmin) {
      message.error('您没有权限访问此页面');
      navigate('/');
      return;
    }
    loadUsers();
  }, [isAdmin, navigate]);

  const loadUsers = useCallback(async () => {
    try {
      setLoading(true);
      const res = await apiClient.get('/api/v1/auth/users');
      setUsers(res.users || res.data || res || []);
    } catch (error: any) {
      // 如果接口不存在则静默处理，显示空列表
      if (error.response?.status !== 404) {
        handleApiError(error, '加载用户列表失败');
      }
      setUsers([]);
    } finally {
      setLoading(false);
    }
  }, []);

  const showModal = (user?: User) => {
    setEditingUser(user || null);
    if (user) {
      form.setFieldsValue(user);
    } else {
      form.resetFields();
    }
    setIsModalVisible(true);
  };

  const handleOk = async () => {
    try {
      const values = await form.validateFields();
      setSubmitting(true);

      if (editingUser) {
        await apiClient.put(`/api/v1/auth/users/${editingUser.id}`, {
          email: values.email,
          role: values.role,
          status: values.status,
        });
        showSuccess('用户更新成功');
      } else {
        await apiClient.post('/api/v1/auth/register', {
          username: values.username,
          email: values.email,
          password: values.password,
          role: values.role,
        });
        showSuccess('用户创建成功');
      }

      setIsModalVisible(false);
      form.resetFields();
      loadUsers();
    } catch (error: any) {
      if (error.errorFields) return; // form validation error
      handleApiError(error, editingUser ? '用户更新失败' : '用户创建失败');
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = (id: string) => {
    Modal.confirm({
      title: '确认删除',
      content: '确定要删除这个用户吗？此操作不可撤销。',
      onOk: async () => {
        try {
          await apiClient.delete(`/api/v1/auth/users/${id}`);
          showSuccess('用户删除成功');
          loadUsers();
        } catch (error: any) {
          handleApiError(error, '用户删除失败');
        }
      },
    });
  };

  const roleMap = {
    admin: { text: '管理员', color: 'red' },
    manager: { text: '经理', color: 'blue' },
    staff: { text: '员工', color: 'green' },
  };

  const statusMap = {
    active: { text: '激活', color: 'green' },
    inactive: { text: '停用', color: 'red' },
  };

  const columns: ColumnsType<User> = [
    {
      title: '头像',
      dataIndex: 'avatar',
      key: 'avatar',
      render: (avatar: string) => <Avatar src={avatar} icon={<UserOutlined />} />,
    },
    { title: '用户名', dataIndex: 'username', key: 'username' },
    { title: '邮箱', dataIndex: 'email', key: 'email' },
    {
      title: '角色',
      dataIndex: 'role',
      key: 'role',
      render: (role: string) => (
        <Tag color={roleMap[role as keyof typeof roleMap]?.color}>
          {roleMap[role as keyof typeof roleMap]?.text || role}
        </Tag>
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (status: string) => (
        <Tag color={statusMap[status as keyof typeof statusMap]?.color}>
          {statusMap[status as keyof typeof statusMap]?.text || status}
        </Tag>
      ),
    },
    { title: '创建时间', dataIndex: 'createdAt', key: 'createdAt' },
    {
      title: '操作',
      key: 'action',
      render: (_, record) => (
        <Space>
          <Button type="link" icon={<EditOutlined />} onClick={() => showModal(record)}>编辑</Button>
          <Button
            type="link"
            danger
            icon={<DeleteOutlined />}
            onClick={() => handleDelete(record.id)}
            disabled={record.role === 'admin'}
          >
            删除
          </Button>
        </Space>
      ),
    },
  ];

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
        <h1 style={{ margin: 0 }}>用户管理</h1>
        <Button icon={<ReloadOutlined />} onClick={loadUsers} loading={loading}>刷新</Button>
      </div>

      <Card>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => showModal()} style={{ marginBottom: 16 }}>
          新建用户
        </Button>
        <Table columns={columns} dataSource={users} rowKey="id" pagination={{ pageSize: 10 }} loading={loading} />
      </Card>

      <Modal
        title={editingUser ? '编辑用户' : '新建用户'}
        open={isModalVisible}
        onOk={handleOk}
        confirmLoading={submitting}
        onCancel={() => { setIsModalVisible(false); form.resetFields(); }}
        width={600}
      >
        <Form form={form} layout="vertical">
          <Form.Item name="username" label="用户名" rules={[{ required: true, message: '请输入用户名' }]}>
            <Input placeholder="请输入用户名" disabled={!!editingUser} />
          </Form.Item>
          <Form.Item
            name="email"
            label="邮箱"
            rules={[{ required: true, message: '请输入邮箱' }, { type: 'email', message: '请输入有效的邮箱地址' }]}
          >
            <Input placeholder="请输入邮箱" />
          </Form.Item>
          {!editingUser && (
            <Form.Item name="password" label="密码" rules={[{ required: true, message: '请输入密码' }, { min: 6, message: '密码至少6位' }]}>
              <Input.Password placeholder="请输入密码" />
            </Form.Item>
          )}
          <Form.Item name="role" label="角色" rules={[{ required: true, message: '请选择角色' }]}>
            <Select placeholder="请选择角色">
              <Option value="admin">管理员</Option>
              <Option value="manager">经理</Option>
              <Option value="staff">员工</Option>
            </Select>
          </Form.Item>
          {editingUser && (
            <Form.Item name="status" label="状态" rules={[{ required: true, message: '请选择状态' }]}>
              <Select placeholder="请选择状态">
                <Option value="active">激活</Option>
                <Option value="inactive">停用</Option>
              </Select>
            </Form.Item>
          )}
        </Form>
      </Modal>
    </div>
  );
};

export default UserManagementPage;
