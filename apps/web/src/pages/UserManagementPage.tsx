import React, { useState, useEffect } from 'react';
import { Card, Table, Button, Modal, Form, Input, Select, message, Space, Tag, Avatar } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { PlusOutlined, EditOutlined, DeleteOutlined, UserOutlined } from '@ant-design/icons';
import { usePermission } from '../hooks/usePermission';
import { useNavigate } from 'react-router-dom';

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
    loadMockData();
  }, [isAdmin, navigate]);

  const loadMockData = () => {
    const mockUsers: User[] = [
      {
        id: '1',
        username: 'admin',
        email: 'admin@zhilian.com',
        role: 'admin',
        avatar: 'https://api.dicebear.com/7.x/avataaars/svg?seed=admin',
        status: 'active',
        createdAt: '2024-01-01'
      },
      {
        id: '2',
        username: 'manager',
        email: 'manager@zhilian.com',
        role: 'manager',
        avatar: 'https://api.dicebear.com/7.x/avataaars/svg?seed=manager',
        status: 'active',
        createdAt: '2024-01-15'
      },
      {
        id: '3',
        username: 'staff',
        email: 'staff@zhilian.com',
        role: 'staff',
        avatar: 'https://api.dicebear.com/7.x/avataaars/svg?seed=staff',
        status: 'active',
        createdAt: '2024-02-01'
      },
      {
        id: '4',
        username: 'zhang_san',
        email: 'zhangsan@zhilian.com',
        role: 'staff',
        avatar: 'https://api.dicebear.com/7.x/avataaars/svg?seed=zhang',
        status: 'active',
        createdAt: '2024-02-10'
      },
      {
        id: '5',
        username: 'li_si',
        email: 'lisi@zhilian.com',
        role: 'manager',
        avatar: 'https://api.dicebear.com/7.x/avataaars/svg?seed=li',
        status: 'inactive',
        createdAt: '2024-02-12'
      }
    ];

    setUsers(mockUsers);
  };

  const showModal = (user?: User) => {
    setEditingUser(user || null);
    if (user) {
      form.setFieldsValue(user);
    } else {
      form.resetFields();
    }
    setIsModalVisible(true);
  };

  const handleOk = () => {
    form.validateFields().then(values => {
      const userData = {
        ...values,
        id: editingUser?.id || Date.now().toString(),
        avatar: `https://api.dicebear.com/7.x/avataaars/svg?seed=${values.username}`,
        createdAt: editingUser?.createdAt || new Date().toISOString().split('T')[0]
      };

      if (editingUser) {
        setUsers(users.map(u => u.id === editingUser.id ? userData : u));
        message.success('用户更新成功');
      } else {
        setUsers([...users, userData]);
        message.success('用户创建成功');
      }

      setIsModalVisible(false);
      form.resetFields();
    });
  };

  const handleDelete = (id: string) => {
    Modal.confirm({
      title: '确认删除',
      content: '确定要删除这个用户吗？',
      onOk: () => {
        setUsers(users.filter(u => u.id !== id));
        message.success('用户删除成功');
      }
    });
  };

  const roleMap = {
    admin: { text: '管理员', color: 'red' },
    manager: { text: '经理', color: 'blue' },
    staff: { text: '员工', color: 'green' }
  };

  const statusMap = {
    active: { text: '激活', color: 'green' },
    inactive: { text: '停用', color: 'red' }
  };

  const columns: ColumnsType<User> = [
    {
      title: '头像',
      dataIndex: 'avatar',
      key: 'avatar',
      render: (avatar: string) => (
        <Avatar src={avatar} icon={<UserOutlined />} />
      )
    },
    {
      title: '用户名',
      dataIndex: 'username',
      key: 'username'
    },
    {
      title: '邮箱',
      dataIndex: 'email',
      key: 'email'
    },
    {
      title: '角色',
      dataIndex: 'role',
      key: 'role',
      render: (role: string) => (
        <Tag color={roleMap[role as keyof typeof roleMap].color}>
          {roleMap[role as keyof typeof roleMap].text}
        </Tag>
      )
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (status: string) => (
        <Tag color={statusMap[status as keyof typeof statusMap].color}>
          {statusMap[status as keyof typeof statusMap].text}
        </Tag>
      )
    },
    {
      title: '创建时间',
      dataIndex: 'createdAt',
      key: 'createdAt'
    },
    {
      title: '操作',
      key: 'action',
      render: (_, record) => (
        <Space>
          <Button
            type="link"
            icon={<EditOutlined />}
            onClick={() => showModal(record)}
          >
            编辑
          </Button>
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
      )
    }
  ];

  return (
    <div>
      <h1 style={{ marginBottom: 24 }}>用户管理</h1>

      <Card>
        <Button
          type="primary"
          icon={<PlusOutlined />}
          onClick={() => showModal()}
          style={{ marginBottom: 16 }}
        >
          新建用户
        </Button>

        <Table
          columns={columns}
          dataSource={users}
          rowKey="id"
          pagination={{ pageSize: 10 }}
        />
      </Card>

      <Modal
        title={editingUser ? '编辑用户' : '新建用户'}
        open={isModalVisible}
        onOk={handleOk}
        onCancel={() => {
          setIsModalVisible(false);
          form.resetFields();
        }}
        width={600}
      >
        <Form form={form} layout="vertical">
          <Form.Item
            name="username"
            label="用户名"
            rules={[{ required: true, message: '请输入用户名' }]}
          >
            <Input placeholder="请输入用户名" />
          </Form.Item>

          <Form.Item
            name="email"
            label="邮箱"
            rules={[
              { required: true, message: '请输入邮箱' },
              { type: 'email', message: '请输入有效的邮箱地址' }
            ]}
          >
            <Input placeholder="请输入邮箱" />
          </Form.Item>

          <Form.Item
            name="role"
            label="角色"
            rules={[{ required: true, message: '请选择角色' }]}
          >
            <Select placeholder="请选择角色">
              <Option value="admin">管理员</Option>
              <Option value="manager">经理</Option>
              <Option value="staff">员工</Option>
            </Select>
          </Form.Item>

          <Form.Item
            name="status"
            label="状态"
            rules={[{ required: true, message: '请选择状态' }]}
          >
            <Select placeholder="请选择状态">
              <Option value="active">激活</Option>
              <Option value="inactive">停用</Option>
            </Select>
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default UserManagementPage;
