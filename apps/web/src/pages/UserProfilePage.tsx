import React, { useState, useCallback, useEffect } from 'react';
import { Card, Form, Input, Button, Descriptions, Tag, Divider, Space, Spin, Avatar } from 'antd';
import { UserOutlined, LockOutlined, SaveOutlined } from '@ant-design/icons';
import { apiClient } from '../services/api';
import { handleApiError, showSuccess } from '../utils/message';

interface UserProfile {
  id: string;
  username: string;
  email?: string;
  full_name?: string;
  role: string;
  store_id?: string;
  is_active: boolean;
  created_at?: string;
  last_login?: string;
  permissions?: string[];
}

const roleColor: Record<string, string> = { admin: 'red', manager: 'orange', staff: 'blue', viewer: 'default' };
const roleLabel: Record<string, string> = { admin: '管理员', manager: '经理', staff: '员工', viewer: '只读' };

const UserProfilePage: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [profileForm] = Form.useForm();
  const [pwdForm] = Form.useForm();
  const [saving, setSaving] = useState(false);
  const [changingPwd, setChangingPwd] = useState(false);

  const loadProfile = useCallback(async () => {
    setLoading(true);
    try {
      const res = await apiClient.get('/auth/me');
      setProfile(res.data);
      profileForm.setFieldsValue({
        full_name: res.data.full_name,
        email: res.data.email,
      });
    } catch (err) {
      handleApiError(err, '加载用户信息失败');
    } finally {
      setLoading(false);
    }
  }, [profileForm]);

  useEffect(() => { loadProfile(); }, [loadProfile]);

  const handleSaveProfile = async (values: { full_name?: string; email?: string }) => {
    setSaving(true);
    try {
      await apiClient.put('/auth/me', values);
      showSuccess('个人信息已更新');
      loadProfile();
    } catch (err) {
      handleApiError(err, '更新个人信息失败');
    } finally {
      setSaving(false);
    }
  };

  const handleChangePassword = async (values: { old_password: string; new_password: string; confirm: string }) => {
    setChangingPwd(true);
    try {
      await apiClient.post('/auth/change-password', {
        old_password: values.old_password,
        new_password: values.new_password,
      });
      showSuccess('密码已修改，请重新登录');
      pwdForm.resetFields();
    } catch (err) {
      handleApiError(err, '修改密码失败');
    } finally {
      setChangingPwd(false);
    }
  };

  return (
    <div style={{ padding: 24, maxWidth: 800, margin: '0 auto' }}>
      <Spin spinning={loading}>
        {profile && (
          <Card style={{ marginBottom: 16 }}>
            <Space align="start" size={24}>
              <Avatar size={64} icon={<UserOutlined />} style={{ background: '#1677ff' }} />
              <div>
                <div style={{ fontSize: 20, fontWeight: 600 }}>{profile.full_name || profile.username}</div>
                <Space style={{ marginTop: 4 }}>
                  <Tag color={roleColor[profile.role] || 'default'}>{roleLabel[profile.role] || profile.role}</Tag>
                  <Tag color={profile.is_active ? 'green' : 'red'}>{profile.is_active ? '活跃' : '已禁用'}</Tag>
                  {profile.store_id && <Tag>{profile.store_id}</Tag>}
                </Space>
              </div>
            </Space>
            <Divider />
            <Descriptions column={{ xs: 1, sm: 2 }} size="small">
              <Descriptions.Item label="用户名">{profile.username}</Descriptions.Item>
              <Descriptions.Item label="邮箱">{profile.email || '-'}</Descriptions.Item>
              <Descriptions.Item label="注册时间">{profile.created_at ? new Date(profile.created_at).toLocaleString() : '-'}</Descriptions.Item>
              <Descriptions.Item label="最后登录">{profile.last_login ? new Date(profile.last_login).toLocaleString() : '-'}</Descriptions.Item>
            </Descriptions>
            {profile.permissions?.length ? (
              <>
                <Divider orientation="left" plain>权限</Divider>
                <Space wrap>
                  {profile.permissions.map(p => <Tag key={p}>{p}</Tag>)}
                </Space>
              </>
            ) : null}
          </Card>
        )}

        <Card title="编辑个人信息" style={{ marginBottom: 16 }}>
          <Form form={profileForm} layout="vertical" onFinish={handleSaveProfile}>
            <Form.Item label="姓名" name="full_name">
              <Input prefix={<UserOutlined />} placeholder="请输入姓名" />
            </Form.Item>
            <Form.Item label="邮箱" name="email" rules={[{ type: 'email', message: '请输入有效邮箱' }]}>
              <Input placeholder="请输入邮箱" />
            </Form.Item>
            <Form.Item>
              <Button type="primary" htmlType="submit" icon={<SaveOutlined />} loading={saving}>保存</Button>
            </Form.Item>
          </Form>
        </Card>

        <Card title="修改密码">
          <Form form={pwdForm} layout="vertical" onFinish={handleChangePassword}>
            <Form.Item label="当前密码" name="old_password" rules={[{ required: true, message: '请输入当前密码' }]}>
              <Input.Password prefix={<LockOutlined />} placeholder="当前密码" />
            </Form.Item>
            <Form.Item label="新密码" name="new_password" rules={[{ required: true, min: 6, message: '密码至少 6 位' }]}>
              <Input.Password prefix={<LockOutlined />} placeholder="新密码（至少 6 位）" />
            </Form.Item>
            <Form.Item
              label="确认新密码"
              name="confirm"
              dependencies={['new_password']}
              rules={[
                { required: true, message: '请确认新密码' },
                ({ getFieldValue }) => ({
                  validator(_, value) {
                    if (!value || getFieldValue('new_password') === value) return Promise.resolve();
                    return Promise.reject(new Error('两次密码不一致'));
                  },
                }),
              ]}
            >
              <Input.Password prefix={<LockOutlined />} placeholder="再次输入新密码" />
            </Form.Item>
            <Form.Item>
              <Button type="primary" htmlType="submit" icon={<LockOutlined />} loading={changingPwd}>修改密码</Button>
            </Form.Item>
          </Form>
        </Card>
      </Spin>
    </div>
  );
};

export default UserProfilePage;
